# ============================================================================
# 0. Instalación de librerías necesarias (ejecutar en terminal)
# ============================================================================
# pip install pandas lxml plotly openpyxl xlsxwriter kaleido

import argparse
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import os
import glob
import xml.etree.ElementTree as ET
from collections import defaultdict

# ============================================================================
# 1. Configuración inicial (valores por defecto, sobrescribibles vía CLI/env)
# ============================================================================
RFC_EMPRESA = os.environ.get('RFC_EMPRESA', 'BMO240603QS0')
TAXA_IVA = 0.16
COEF_UTILIDAD = float(os.environ.get('COEF_UTILIDAD', '0.1029'))

# Persona Moral → tasa fija 30% (Art. 9 LISR)
TASA_ISR_PM = 0.30

# Datos de la Declaración Anual 2025 (presentada 25/03/2026)
DECLARACION_2025 = {
    'isr_causado': 51472.00,
    'ejercicio': 2025,
    'presentacion': '25/03/2026',
}

# ============================================================================
#   Tarifa ISR 2026 - Anexo 8 RMF 2026 (DOF 28/12/2025) — Personas Físicas
#   Se mantiene como referencia; NO aplica para Personas Morales (tasa fija 30%)
# ============================================================================
TARIFA_ISR_2026 = [
    (0.01, 10135.11, 0.00, 1.92),
    (10135.12, 86022.11, 194.59, 6.40),
    (86022.12, 151176.19, 5051.37, 10.88),
    (151176.20, 175735.66, 12140.13, 16.00),
    (175735.67, 210403.69, 16069.64, 17.92),
    (210403.70, 424353.97, 22282.14, 21.36),
    (424353.98, 668840.14, 67981.92, 23.52),
    (668840.15, 1276925.98, 125485.07, 30.00),
    (1276925.99, 1702567.97, 307910.81, 32.00),
    (1702567.98, 5107703.92, 444116.23, 34.00),
    (5107703.93, float('inf'), 1601862.46, 35.00),
]


def aplicar_tarifa(base_gravable, tarifa):
    """Aplica la tarifa progresiva de ISR (Art. 96 o 152 LISR)."""
    if base_gravable <= 0:
        return 0.0
    for lim_inf, lim_sup, cuota_fija, porcentaje in tarifa:
        if lim_inf <= base_gravable <= lim_sup:
            excedente = base_gravable - (lim_inf - 0.01)
            return cuota_fija + excedente * (porcentaje / 100)
    lim_inf, _, cuota_fija, porcentaje = tarifa[-1]
    excedente = base_gravable - (lim_inf - 0.01)
    return cuota_fija + excedente * (porcentaje / 100)


# Palabras clave para detectar gastos potencialmente no deducibles
NO_DEDUCIBLE_KEYWORDS = [
    'multa', 'penalización', 'penalizacion', 'recargo',
    'interés moratorio', 'interes moratorio', 'donativo',
    'obsequio', 'regalo', 'gasto personal', 'actualización',
    'actualizacion', 'interés',
]

# ============================================================================
# 2. Función para extraer datos de un CFDI XML
# ============================================================================
def extraer_datos_cfdi(ruta_xml):
    """Extrae datos fiscales de un CFDI XML (soporta CFDI 3.3, 3.2 y 4.0)."""
    try:
        tree = ET.parse(ruta_xml)
        root = tree.getroot()
        comprobante = root.attrib

        version = comprobante.get('Version', comprobante.get('version', '3.3'))
        ns_cfdi = {
            '3.3': 'http://www.sat.gob.mx/cfd/3',
            '3.2': 'http://www.sat.gob.mx/cfd/3',
            '4.0': 'http://www.sat.gob.mx/cfd/4',
        }.get(version, 'http://www.sat.gob.mx/cfd/3')

        ns = {
            'cfdi': ns_cfdi,
            'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
        }

        emisor = root.find('cfdi:Emisor', ns)
        receptor = root.find('cfdi:Receptor', ns)
        timbre = root.find('.//tfd:TimbreFiscalDigital', ns)
        conceptos = root.findall('cfdi:Conceptos/cfdi:Concepto', ns)

        uuid = timbre.attrib.get('UUID') if timbre is not None else comprobante.get('Folio')
        serie = comprobante.get('Serie', '')
        folio = comprobante.get('Folio', '')
        fecha = comprobante.get('Fecha', '')
        subtotal = float(comprobante.get('SubTotal', 0))
        total = float(comprobante.get('Total', 0))
        rfc_emisor = emisor.attrib.get('Rfc') if emisor is not None else None
        rfc_receptor = receptor.attrib.get('Rfc') if receptor is not None else None
        nombre_emisor = emisor.attrib.get('Nombre', '') if emisor is not None else ''
        nombre_receptor = receptor.attrib.get('Nombre', '') if receptor is not None else ''
        tipo = comprobante.get('TipoDeComprobante', '')

        conceptos_list = [
            c.attrib.get('Descripcion', '') for c in conceptos
        ]
        conceptos_str = ' | '.join(conceptos_list)

        # IVA: primero del nodo Impuestos global, luego de cada concepto
        iva = 0.0
        impuestos = root.find('cfdi:Impuestos', ns)
        if impuestos is not None:
            traslados = impuestos.find('cfdi:Traslados', ns)
            if traslados is not None:
                for traslado in traslados.findall('cfdi:Traslado', ns):
                    if traslado.attrib.get('Impuesto') == '002':
                        iva += float(traslado.attrib.get('Importe', 0))

        if iva == 0:
            for c in conceptos:
                c_impuestos = c.find('cfdi:Impuestos', ns)
                if c_impuestos is not None:
                    c_traslados = c_impuestos.find('cfdi:Traslados', ns)
                    if c_traslados is not None:
                        for traslado in c_traslados.findall('cfdi:Traslado', ns):
                            if traslado.attrib.get('Impuesto') == '002':
                                iva += float(traslado.attrib.get('Importe', 0))

        es_no_deducible = any(
            kw in conceptos_str.lower() for kw in NO_DEDUCIBLE_KEYWORDS
        )

        return {
            'UUID': uuid,
            'Serie': serie,
            'Folio': folio,
            'Fecha Emisión': fecha,
            'RFC Emisor': rfc_emisor,
            'Nombre Emisor': nombre_emisor,
            'RFC Receptor': rfc_receptor,
            'Nombre Receptor': nombre_receptor,
            'Subtotal': subtotal,
            'Total': total,
            'IVA': iva,
            'Tipo': tipo,
            'Conceptos': conceptos_str,
            'Es_No_Deducible': es_no_deducible,
        }
    except Exception as e:
        print(f"Error al procesar {ruta_xml}: {str(e)}")
        return None

# ============================================================================
# 3. Carga masiva desde una carpeta
# ============================================================================
def cargar_cfdi_masivo(ruta_carpeta):
    """
    Recibe una carpeta, busca todos los archivos .xml y los clasifica en emitidos y recibidos.
    Retorna dos DataFrames: df_emitidos, df_recibidos.
    """
    archivos_xml = glob.glob(os.path.join(ruta_carpeta, "**", "*.xml"), recursive=True)
    print(f"📂 Se encontraron {len(archivos_xml)} archivos XML.")

    datos_emitidos = []
    datos_recibidos = []
    uuids_vistos = set()

    for xml_path in archivos_xml:
        datos = extraer_datos_cfdi(xml_path)
        if datos is None:
            continue

        if datos['Tipo'] in ('N', 'P'):
            continue

        if datos['UUID'] in uuids_vistos:
            continue
        uuids_vistos.add(datos['UUID'])

        if datos['RFC Emisor'] == RFC_EMPRESA:
            datos_emitidos.append(datos)
        elif datos['RFC Receptor'] == RFC_EMPRESA:
            datos_recibidos.append(datos)

    df_emitidos = pd.DataFrame(datos_emitidos)
    df_recibidos = pd.DataFrame(datos_recibidos)

    # Convertir fechas a datetime
    if not df_emitidos.empty:
        df_emitidos['Fecha Emisión'] = pd.to_datetime(df_emitidos['Fecha Emisión'])
    if not df_recibidos.empty:
        df_recibidos['Fecha Emisión'] = pd.to_datetime(df_recibidos['Fecha Emisión'])

    print(f"✅ Facturas emitidas: {len(df_emitidos)} | Recibidas: {len(df_recibidos)}")
    return df_emitidos, df_recibidos

# ============================================================================
# 4. Agregación mensual de ingresos y gastos
# ============================================================================
def extraer_ingresos_gastos(df_emitidos, df_recibidos):
    if not df_emitidos.empty:
        ingresos = df_emitidos.groupby(df_emitidos['Fecha Emisión'].dt.to_period('M')).agg({
            'Subtotal': 'sum',
            'IVA': 'sum'
        }).rename(columns={'Subtotal': 'Ingresos Gravables', 'IVA': 'IVA Trasladado'})
    else:
        ingresos = pd.DataFrame(columns=['Ingresos Gravables', 'IVA Trasladado'])

    if not df_recibidos.empty:
        gastos = df_recibidos.groupby(df_recibidos['Fecha Emisión'].dt.to_period('M')).agg({
            'Subtotal': 'sum',
            'IVA': 'sum'
        }).rename(columns={'Subtotal': 'Gastos Deducibles', 'IVA': 'IVA Acreditable'})

        no_deducibles = df_recibidos[df_recibidos['Es_No_Deducible']]
        if not no_deducibles.empty:
            gastos_no_ded = no_deducibles.groupby(
                no_deducibles['Fecha Emisión'].dt.to_period('M')
            ).agg({'Subtotal': 'sum'}).rename(columns={'Subtotal': 'Posibles No Deducibles'})
            gastos = gastos.join(gastos_no_ded, how='left').fillna(0)
        else:
            gastos['Posibles No Deducibles'] = 0.0

        total_no_ded = gastos['Posibles No Deducibles'].sum()
        if total_no_ded > 0:
            print(f"⚠️  Se detectaron ${total_no_ded:,.2f} en gastos potencialmente NO deducibles.")
    else:
        gastos = pd.DataFrame(columns=['Gastos Deducibles', 'IVA Acreditable', 'Posibles No Deducibles'])

    resultado = ingresos.join(gastos, how='outer').fillna(0)
    resultado.index = resultado.index.astype(str)
    return resultado

# ============================================================================
# 5. Cálculo de ISR — Persona Moral (tasa fija 30%, Art. 9 LISR)
#    Pagos provisionales: coeficiente × ingreso × 30% (Art. 14 LISR)
#    Declaración anual: utilidad fiscal × 30%
# ============================================================================
def calcular_isr_provisionales(datos_mensuales, coef, tasa=TASA_ISR_PM):
    """ISR provisional mensual persona moral: coef × ingreso × tasa fija."""
    meses = datos_mensuales.sort_index()
    bases_mensuales = meses['Ingresos Gravables'] * coef
    bases_acumuladas = bases_mensuales.cumsum()
    isr_acumulado = bases_acumuladas * tasa
    isr_mensual = isr_acumulado.diff().fillna(isr_acumulado.iloc[0])
    return isr_mensual.clip(lower=0)

def calcular_anual(datos_mensuales, tasa=TASA_ISR_PM):
    total_ingresos = datos_mensuales['Ingresos Gravables'].sum()
    total_gastos = datos_mensuales['Gastos Deducibles'].sum()
    utilidad_fiscal = total_ingresos - total_gastos
    isr_causado = utilidad_fiscal * tasa
    isr_pagado = datos_mensuales['ISR Provisional'].sum()
    isr_a_pagar = max(isr_causado - isr_pagado, 0)
    iva_anual = datos_mensuales['IVA a Pagar'].sum()
    return {
        'Ingresos': total_ingresos,
        'Gastos': total_gastos,
        'Gastos No Deducibles Detectados': datos_mensuales['Posibles No Deducibles'].sum(),
        'Utilidad Fiscal': utilidad_fiscal,
        'ISR Causado (30% PM)': isr_causado,
        'ISR Pagado (Provisional)': isr_pagado,
        'ISR Anual a Pagar': isr_a_pagar,
        'IVA Anual a Pagar': iva_anual,
    }

# ============================================================================
# 6. Dashboard y exportación (igual que antes)
# ============================================================================
def generar_dashboard(datos_mensuales, resumen_anual):
    fig1 = px.bar(datos_mensuales, x=datos_mensuales.index,
                  y=['Ingresos Gravables', 'Gastos Deducibles'],
                  title="📈 Ingresos vs Gastos por mes",
                  barmode='group', labels={'value': 'MXN', 'variable': 'Concepto'})
    fig2 = px.line(datos_mensuales, x=datos_mensuales.index,
                   y=['ISR Provisional', 'IVA a Pagar'],
                   title="💰 Impuestos mensuales",
                   markers=True, labels={'value': 'MXN'})

    # Mostrar resumen en consola
    print("\n=== 📊 RESUMEN ANUAL ===")
    for k, v in resumen_anual.items():
        print(f"{k}: ${v:,.2f}")

    fig1.show()
    fig2.show()
    return fig1, fig2

def exportar_reportes(datos_mensuales, resumen_anual, nombre_archivo="Reporte_Fiscal_2026"):
    # Excel
    with pd.ExcelWriter(f"{nombre_archivo}.xlsx", engine='openpyxl') as writer:
        datos_mensuales.to_excel(writer, sheet_name='Datos Mensuales', index=True)
        df_resumen = pd.DataFrame(list(resumen_anual.items()), columns=['Concepto', 'Monto'])
        df_resumen.to_excel(writer, sheet_name='Resumen Anual', index=False)

    # PDF de gráficas (requiere kaleido)
    try:
        fig1, fig2 = generar_dashboard(datos_mensuales, resumen_anual)  # reusamos
        fig1.write_image(f"{nombre_archivo}_ingresos_gastos.pdf")
        fig2.write_image(f"{nombre_archivo}_impuestos.pdf")
        print("✅ PDF generados correctamente.")
    except Exception as e:
        print(f"⚠️ No se pudieron generar PDF: {e}")

# ============================================================================
# 7. Ejecución principal
# ============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Calculadora Fiscal CFDI')
    parser.add_argument('--rfc', default=os.environ.get('RFC_EMPRESA', 'BMO240603QS0'),
                        help='RFC de la empresa')
    parser.add_argument('--carpeta',
                        default='/home/irvin/Documentos/Proyectos/calculadora_fiscal/cfdis_para_procesar',
                        help='Carpeta con CFDIs XML')
    parser.add_argument('--coef', type=float, default=COEF_UTILIDAD,
                        help='Coeficiente de utilidad (anual anterior)')
    parser.add_argument('--excel-emitidos', help='Archivo Excel respaldo facturas emitidas')
    parser.add_argument('--excel-recibidos', help='Archivo Excel respaldo facturas recibidas')
    parser.add_argument('--output', default='Reporte_Fiscal_2026',
                        help='Nombre base del reporte de salida')
    args = parser.parse_args()

    RFC_EMPRESA = args.rfc
    COEF_UTILIDAD = args.coef

    df_emitidos, df_recibidos = cargar_cfdi_masivo(args.carpeta)

    if df_emitidos.empty and df_recibidos.empty:
        print("No se encontraron CFDIs XML. Intentando carga desde Excel...")
        if args.excel_emitidos and args.excel_recibidos:
            df_emitidos = pd.read_excel(args.excel_emitidos)
            df_recibidos = pd.read_excel(args.excel_recibidos)
            for df in (df_emitidos, df_recibidos):
                if not df.empty:
                    df['Fecha Emisión'] = pd.to_datetime(df['Fecha Emisión'])
            print(f"✅ Cargados desde Excel: {len(df_emitidos)} emitidas, {len(df_recibidos)} recibidas")
        else:
            print("Usa --excel-emitidos y --excel-recibidos para cargar desde Excel.")
            exit()

    datos_mensuales = extraer_ingresos_gastos(df_emitidos, df_recibidos)
    datos_mensuales['ISR Provisional'] = calcular_isr_provisionales(datos_mensuales, COEF_UTILIDAD)
    datos_mensuales['IVA a Pagar'] = (datos_mensuales['IVA Trasladado'] - datos_mensuales['IVA Acreditable']).clip(lower=0)

    resumen = calcular_anual(datos_mensuales)

    generar_dashboard(datos_mensuales, resumen)
    exportar_reportes(datos_mensuales, resumen, args.output)

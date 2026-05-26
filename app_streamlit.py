"""
Dashboard Fiscal 2026 — Streamlit App
Procesa CFDIs, calcula ISR/IVA, y genera visualizaciones interactivas.
Copy profesional con enfoque de planeación fiscal estratégica.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys, os, glob, json
from datetime import datetime
from collections import Counter, defaultdict
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calculadora_fiscal import (
    extraer_datos_cfdi, cargar_cfdi_masivo, extraer_ingresos_gastos,
    calcular_isr_provisionales, calcular_anual, aplicar_tarifa,
    RFC_EMPRESA, COEF_UTILIDAD, TASA_ISR_PM, TARIFA_ISR_2026, TAXA_IVA,
    NO_DEDUCIBLE_KEYWORDS, DECLARACION_2025
)

# ─── CONFIGURACIÓN VISUAL ────────────────────────────────────────────────
COLOR_PRIMARY = "#0A2540"
COLOR_SECONDARY = "#C8A951"
COLOR_ACCENT = "#00B4D8"
COLOR_SUCCESS = "#2ECC71"
COLOR_WARNING = "#F39C12"
COLOR_DANGER = "#E74C3C"
COLOR_BG = "#F8F9FA"

st.set_page_config(
    page_title="Dashboard Fiscal 2026 — BRMN MOTORS COMPANY",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');
    * {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: {COLOR_BG}; }}
    .block-container {{ padding-top: 1.5rem; padding-bottom: 3rem; }}

    .main-header {{ font-size: 2.8rem; font-weight: 800; color: {COLOR_PRIMARY};
                     letter-spacing: -1px; line-height: 1.1; }}
    .main-sub {{ font-size: 1rem; color: #5A7A9A; font-weight: 300; margin-top: -0.3rem; }}

    .kpi-card {{ background: linear-gradient(135deg, {COLOR_PRIMARY}, #1A3A5C);
                 padding: 1.2rem 1.5rem; border-radius: 14px; color: white;
                 box-shadow: 0 8px 24px rgba(10,37,64,0.12);
                 border: 1px solid rgba(255,255,255,0.06); }}
    .kpi-label {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
                  letter-spacing: 1px; opacity: 0.7; }}
    .kpi-value {{ font-size: 2rem; font-weight: 700; line-height: 1.2; }}
    .kpi-delta {{ font-size: 0.85rem; font-weight: 500; margin-top: 0.2rem; }}

    .kpi-card-gold {{ background: linear-gradient(135deg, #B8860B, {COLOR_SECONDARY});
                      padding: 1.2rem 1.5rem; border-radius: 14px; color: white;
                      box-shadow: 0 8px 24px rgba(200,169,81,0.2); }}
    .kpi-card-danger {{ background: linear-gradient(135deg, #8B0000, {COLOR_DANGER});
                        padding: 1.2rem 1.5rem; border-radius: 14px; color: white;
                        box-shadow: 0 8px 24px rgba(231,76,60,0.15); }}
    .kpi-card-green {{ background: linear-gradient(135deg, #1B5E20, {COLOR_SUCCESS});
                       padding: 1.2rem 1.5rem; border-radius: 14px; color: white;
                       box-shadow: 0 8px 24px rgba(46,204,113,0.15); }}

    .card {{ background: white; border-radius: 14px; padding: 1.5rem;
             box-shadow: 0 2px 12px rgba(0,0,0,0.04);
             border: 1px solid rgba(0,0,0,0.04); }}
    .card-title {{ font-size: 0.9rem; font-weight: 700; color: {COLOR_PRIMARY};
                   text-transform: uppercase; letter-spacing: 1px; margin-bottom: 1rem; }}

    .insight {{ background: #FFFEF5; border-left: 4px solid {COLOR_SECONDARY};
                padding: 1rem 1.2rem; border-radius: 0 8px 8px 0; margin: 0.8rem 0;
                font-size: 0.9rem; color: #4A4A4A; }}
    .insight strong {{ color: {COLOR_PRIMARY}; }}

    .tax-bracket {{ padding: 0.4rem 0.6rem; border-radius: 6px; font-size: 0.8rem;
                    margin: 0.15rem 0; color: white; text-align: center;
                    transition: all 0.2s; }}
    .tax-bracket:hover {{ transform: scale(1.03); opacity: 0.9; }}

    .section-divider {{ border: none; height: 2px;
                        background: linear-gradient(90deg, {COLOR_PRIMARY}, transparent); }}

    h2 {{ color: {COLOR_PRIMARY}; font-weight: 700; font-size: 1.5rem; }}
    h3 {{ color: {COLOR_PRIMARY}; font-weight: 600; font-size: 1.1rem; }}

    .stTabs [data-baseweb="tab-list"] {{ gap: 0.5rem; }}
    .stTabs [data-baseweb="tab"] {{ border-radius: 8px 8px 0 0; padding: 0.5rem 1rem; }}

    .footer {{ text-align: center; color: #999; font-size: 0.75rem; margin-top: 3rem; }}
</style>
""", unsafe_allow_html=True)

# ─── CONSTANTES ──────────────────────────────────────────────────────────
RUTA_CFDI = "/home/irvin/Documentos/Proyectos/calculadora_fiscal/cfdis_para_procesar"

# Datos de la Constancia de Situación Fiscal
NOMBRE_EMPRESA = "BRMN MOTORS COMPANY, S.A. de C.V."
RFC = "BMO240603QS0"
REGIMEN = "Régimen General de Ley Personas Morales"
CAPITAL = "Sociedad Anónima de Capital Variable"
ACTIVIDAD = "Reparación mecánica en general de automóviles y camiones"
DOMICILIO = "Lafayette #93, Int. 102, Col. Anzures, Miguel Hidalgo, CDMX, CP 11590"
INICIO_OPS = "03 de junio de 2024"

OBLIGACIONES = [
    ("Pago definitivo mensual de IVA", "Día 17 del mes siguiente"),
    ("Retenciones ISR asimilados a salarios", "Día 17 del mes siguiente"),
    ("Declaración de proveedores de IVA (DIOT)", "Último día del mes siguiente"),
    ("Declaración anual ISR personas morales", "Tres meses posteriores al cierre"),
    ("Pago provisional mensual ISR", "Día 17 del mes siguiente"),
]

EJERCICIO = 2026

# ─── CARGA DE DATOS (CACHED) ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Procesando 438 CFDIs...")
def procesar_todo():
    df_emit, df_recib = cargar_cfdi_masivo(RUTA_CFDI)
    return df_emit, df_recib

@st.cache_data(ttl=3600)
def analisis_detallado(df_emit, df_recib):
    info = {}

    # ── Emitidos ──
    if not df_emit.empty:
        info['total_emitidos'] = len(df_emit)
        info['total_ingresos'] = df_emit['Subtotal'].sum()
        info['total_iva_emitido'] = df_emit['IVA'].sum()
        info['promedio_ingreso'] = df_emit['Subtotal'].mean()
        info['mediana_ingreso'] = df_emit['Subtotal'].median()

        # Clientes con nombre (excluir la propia empresa)
        df_emit['Cliente'] = df_emit.apply(
            lambda r: f"{r.get('Nombre Receptor', '')} ({r['RFC Receptor']})" if r.get('Nombre Receptor')
            else r['RFC Receptor'], axis=1
        )
        top_cli = df_emit[df_emit['RFC Receptor'] != RFC_EMPRESA].groupby(
            ['RFC Receptor', 'Cliente']
        ).agg(
            Total=('Subtotal', 'sum'),
            Facturas=('UUID', 'count'),
            Promedio=('Subtotal', 'mean')
        ).sort_values('Total', ascending=False).head(15).reset_index()
        top_cli = top_cli[['Cliente', 'Total', 'Facturas', 'Promedio']].rename(
            columns={'Cliente': 'Cliente'}
        )
        info['top_clientes'] = top_cli

        meses_emit = df_emit.copy()
        meses_emit['Mes'] = meses_emit['Fecha Emisión'].dt.to_period('M').astype(str)
        info['ingresos_mensual'] = meses_emit.groupby('Mes').agg(
            Ingresos=('Subtotal', 'sum'),
            Facturas=('UUID', 'count')
        )
    else:
        info.update(total_emitidos=0, total_ingresos=0, total_iva_emitido=0,
                    promedio_ingreso=0, mediana_ingreso=0)
        info['top_clientes'] = pd.DataFrame(columns=['Cliente','Total','Facturas','Promedio'])
        info['ingresos_mensual'] = pd.DataFrame()

    # ── Recibidos ──
    if not df_recib.empty:
        info['total_recibidos'] = len(df_recib)
        info['total_gastos'] = df_recib['Subtotal'].sum()
        info['total_iva_recibido'] = df_recib['IVA'].sum()

        # Proveedores con nombre
        df_recib['Proveedor'] = df_recib.apply(
            lambda r: f"{r.get('Nombre Emisor', '')} ({r['RFC Emisor']})" if r.get('Nombre Emisor')
            else r['RFC Emisor'], axis=1
        )
        top_prov = df_recib.groupby(['RFC Emisor', 'Proveedor']).agg(
            Total=('Subtotal', 'sum'),
            Facturas=('UUID', 'count'),
            Promedio=('Subtotal', 'mean')
        ).sort_values('Total', ascending=False).head(15).reset_index()
        top_prov = top_prov[['Proveedor', 'Total', 'Facturas', 'Promedio']].rename(
            columns={'Proveedor': 'Proveedor'}
        )
        info['top_proveedores'] = top_prov

        no_ded = df_recib[df_recib['Es_No_Deducible']]
        info['total_no_deducible'] = no_ded['Subtotal'].sum() if not no_ded.empty else 0
        info['no_deducibles'] = no_ded if not no_ded.empty else pd.DataFrame()

        meses_rec = df_recib.copy()
        meses_rec['Mes'] = meses_rec['Fecha Emisión'].dt.to_period('M').astype(str)
        info['gastos_mensual'] = meses_rec.groupby('Mes').agg(
            Gastos=('Subtotal', 'sum'),
            Facturas=('UUID', 'count')
        )
    else:
        info.update(total_recibidos=0, total_gastos=0, total_iva_recibido=0,
                    total_no_deducible=0)
        info['top_proveedores'] = pd.DataFrame(columns=['Proveedor','Total','Facturas','Promedio'])
        info['no_deducibles'] = pd.DataFrame()
        info['gastos_mensual'] = pd.DataFrame()

    # ── Mensual agregado ──
    mensual = extraer_ingresos_gastos(df_emit, df_recib)
    if not mensual.empty:
        mensual = mensual.sort_index()
        mensual['ISR Provisional'] = calcular_isr_provisionales(mensual, COEF_UTILIDAD)
        mensual['IVA a Pagar'] = (mensual['IVA Trasladado'] - mensual['IVA Acreditable']).clip(lower=0)
        info['datos_mensuales'] = mensual
        info['resumen_anual'] = calcular_anual(mensual)

        isr_prov_total = mensual['ISR Provisional'].sum()
        iva_total = mensual['IVA a Pagar'].sum()
        info['total_isr_provisional'] = isr_prov_total
        info['total_iva_pagar'] = iva_total

        carga_isr = (isr_prov_total / info['total_ingresos'] * 100) if info['total_ingresos'] > 0 else 0
        carga_iva = (iva_total / info['total_ingresos'] * 100) if info['total_ingresos'] > 0 else 0
        info['carga_isr'] = carga_isr
        info['carga_iva'] = carga_iva
        info['carga_total'] = carga_isr + carga_iva
    else:
        info['datos_mensuales'] = pd.DataFrame()
        info['resumen_anual'] = {}
        info['total_isr_provisional'] = 0
        info['total_iva_pagar'] = 0
        info['carga_isr'] = 0
        info['carga_iva'] = 0
        info['carga_total'] = 0

    info['utilidad_fiscal'] = info['total_ingresos'] - info['total_gastos']
    margen = ((info['utilidad_fiscal'] / info['total_ingresos']) * 100
              if info['total_ingresos'] > 0 else 0)
    info['margen_neto'] = margen

    # Clientes que concentran más del 50% de ingresos
    if not info['top_clientes'].empty:
        top = info['top_clientes']
        top['%Acum'] = top['Total'].cumsum() / info['total_ingresos'] * 100
        umbral = top[top['%Acum'] <= 50]
        info['clientes_50pct'] = len(umbral)
    else:
        info['clientes_50pct'] = 0

    return info

# ─── FUNCIONES DE VISUALIZACIÓN ──────────────────────────────────────────

def sidebar_info(rfc, nombre):
    with st.sidebar:
        st.markdown(f"""<div style='text-align:center;padding:0.8rem 0;'>
            <div style='background:{COLOR_PRIMARY};width:56px;height:56px;border-radius:14px;
                 display:flex;align-items:center;justify-content:center;margin:0 auto 0.5rem;'>
                <span style='color:white;font-weight:800;font-size:1.5rem;'>BM</span></div>
            <div style='font-size:1.1rem;font-weight:700;color:{COLOR_PRIMARY};'>BRMN MOTORS</div>
            <div style='font-size:0.65rem;color:#999;text-transform:uppercase;letter-spacing:2px;'>
            S.A. de C.V.</div></div>""",
            unsafe_allow_html=True)
        st.markdown(f"---")

        st.markdown(f"**{nombre}**")
        st.caption(f"RFC: {rfc}")
        st.caption(f"Inicio: {INICIO_OPS}")
        st.markdown("---")

        st.markdown("#### 🔧 Actividad")
        st.caption(ACTIVIDAD)
        st.markdown("---")

        st.markdown("#### 📍 Domicilio")
        st.caption(DOMICILIO)
        st.markdown("---")

        st.markdown("#### 📋 Régimen")
        st.caption(REGIMEN)
        st.caption(CAPITAL)
        st.markdown("---")

        st.markdown("#### 📅 Periodo Analizado")
        st.caption("Enero — Mayo 2026")
        st.markdown("---")

        st.markdown("#### ⚙️ Coeficiente")
        st.caption(f"Utilidad: {COEF_UTILIDAD*100:.2f}%")
        st.caption(f"(Decl. anual {EJERCICIO-1})")
        st.markdown("---")

        isr_2025 = DECLARACION_2025['isr_causado']
        st.markdown("#### 📅 Declaración 2025")
        st.caption(f"ISR Causado: $ {isr_2025:,.0f}")
        st.caption(f"Presentada: {DECLARACION_2025['presentacion']}")
        st.caption(f"Tasa: {TASA_ISR_PM*100:.0f}% fija PM (Art. 9 LISR)")
        st.markdown("---")

        st.markdown("#### 📋 Obligaciones Fiscales")
        for obl, ven in OBLIGACIONES:
            st.markdown(f"""<div style='font-size:0.75rem;padding:0.2rem 0;border-bottom:1px solid
                         rgba(0,0,0,0.04);'>
                         <span style='color:{COLOR_PRIMARY};font-weight:600;'>◉</span> {obl}
                         <br><span style='color:#999;font-size:0.65rem;'>{ven}</span></div>""",
                        unsafe_allow_html=True)
        st.markdown("---")

        st.markdown("#### 📎 Reportes")
        if st.button("📥 Exportar a Excel", use_container_width=True):
            from calculadora_fiscal import exportar_reportes
            try:
                exportar_reportes(
                    st.session_state.get('datos_mensuales', pd.DataFrame()),
                    st.session_state.get('resumen_anual', {}),
                    "reportes/Reporte_Fiscal_2026"
                )
                st.success("✅ Reporte generado en reportes/")
            except Exception as e:
                st.error(f"Error: {e}")

        st.markdown("---")
        reloj = datetime.now().strftime("%d/%m/%Y %H:%M")
        st.caption(f"🕐 Actualizado: {reloj}")


def metricas_principales(info):
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-label">📈 Ingresos Brutos</div>
            <div class="kpi-value">${info['total_ingresos']:,.0f}</div>
            <div class="kpi-delta">{info['total_emitidos']} facturas emitidas</div></div>""",
            unsafe_allow_html=True)

    with c2:
        st.markdown(f"""<div class="kpi-card-green">
            <div class="kpi-label">📉 Gastos Deducibles</div>
            <div class="kpi-value">${info['total_gastos']:,.0f}</div>
            <div class="kpi-delta">{info['total_recibidos']} facturas recibidas</div></div>""",
            unsafe_allow_html=True)

    util = info['utilidad_fiscal']
    color_util = "kpi-card" if util > 0 else "kpi-card-danger"
    with c3:
        st.markdown(f"""<div class="{color_util}">
            <div class="kpi-label">💰 Utilidad Fiscal</div>
            <div class="kpi-value">${util:,.0f}</div>
            <div class="kpi-delta">Margen {info['margen_neto']:.1f}%</div></div>""",
            unsafe_allow_html=True)

    with c4:
        isr_causado = info['resumen_anual'].get('ISR Causado (30% PM)', 0)
        st.markdown(f"""<div class="kpi-card-gold">
            <div class="kpi-label">🏛️ ISR Causado</div>
            <div class="kpi-value">${isr_causado:,.0f}</div>
            <div class="kpi-delta">{TASA_ISR_PM*100:.0f}% fijo (Art. 9 LISR PM)</div></div>""",
            unsafe_allow_html=True)

    with c5:
        iva = info['total_iva_pagar']
        color_iva = "kpi-card-danger" if iva > 100000 else "kpi-card-gold"
        with c5:
            st.markdown(f"""<div class="{color_iva}">
                <div class="kpi-label">🧾 IVA a Pagar</div>
                <div class="kpi-value">${iva:,.0f}</div>
                <div class="kpi-delta">Tasa {TAXA_IVA*100:.0f}%</div></div>""",
                unsafe_allow_html=True)


def grafico_ingresos_gastos(info, key="ingresos_gastos"):
    df = info['datos_mensuales'].copy()
    if df.empty:
        return

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df.index, y=df['Ingresos Gravables'],
        name='Ingresos', marker_color='#0A2540',
        hovertemplate='<b>%{x}</b><br>Ingresos: $%{y:,.2f}<extra></extra>'
    ))
    fig.add_trace(go.Bar(
        x=df.index, y=df['Gastos Deducibles'],
        name='Gastos', marker_color='#C8A951',
        hovertemplate='<b>%{x}</b><br>Gastos: $%{y:,.2f}<extra></extra>'
    ))

    util_meses = df['Ingresos Gravables'] - df['Gastos Deducibles']
    fig.add_trace(go.Scatter(
        x=df.index, y=util_meses,
        name='Utilidad', mode='lines+markers',
        line=dict(color='#2ECC71', width=3),
        marker=dict(size=8, symbol='diamond'),
        hovertemplate='<b>%{x}</b><br>Utilidad: $%{y:,.2f}<extra></extra>'
    ))

    fig.update_layout(
        barmode='group', height=380,
        hovermode='x unified',
        legend=dict(orientation='h', y=1.12, x=0, font=dict(size=12)),
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(title='MXN', tickformat='$,.0f', gridcolor='rgba(0,0,0,0.05)'),
        xaxis=dict(gridcolor='rgba(0,0,0,0.05)'),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    )
    st.plotly_chart(fig, key=key, use_container_width=True)


def grafico_impuestos_mensuales(info):
    df = info['datos_mensuales'].copy()
    if df.empty:
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ISR Provisional'],
        name='ISR Provisional', mode='lines+markers',
        line=dict(color='#C8A951', width=3),
        marker=dict(size=8),
        fill='tozeroy', fillcolor='rgba(200,169,81,0.1)',
        hovertemplate='<b>%{x}</b><br>ISR: $%{y:,.2f}<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=df.index, y=df['IVA a Pagar'],
        name='IVA a Pagar', mode='lines+markers',
        line=dict(color='#E74C3C', width=3),
        marker=dict(size=8),
        fill='tozeroy', fillcolor='rgba(231,76,60,0.1)',
        hovertemplate='<b>%{x}</b><br>IVA: $%{y:,.2f}<extra></extra>'
    ))

    fig.update_layout(
        height=380, hovermode='x unified',
        legend=dict(orientation='h', y=1.12, x=0, font=dict(size=12)),
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis=dict(title='MXN', tickformat='$,.0f', gridcolor='rgba(0,0,0,0.05)'),
        xaxis=dict(gridcolor='rgba(0,0,0,0.05)'),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
    )
    st.plotly_chart(fig, use_container_width=True)


def top_clientes_chart(info):
    df = info['top_clientes'].head(10)
    if df.empty:
        return

    fig = px.bar(
        df, y='Cliente', x='Total', text='Total',
        orientation='h', height=400,
        color='Total', color_continuous_scale=['#C8A951', '#0A2540'],
    )
    fig.update_traces(
        texttemplate='$%{x:,.0f}', textposition='outside',
        hovertemplate='<b>%{y}</b><br>Total: $%{x:,.2f}<br>Facturas: %{customdata[0]}<extra></extra>',
        customdata=df[['Facturas']]
    )
    fig.update_layout(
        xaxis=dict(tickformat='$,.0f', gridcolor='rgba(0,0,0,0.05)'),
        yaxis=dict(title='', autorange='reversed'),
        coloraxis_showscale=False,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=60, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def top_proveedores_chart(info):
    df = info['top_proveedores'].head(10)
    if df.empty:
        return

    fig = px.bar(
        df, y='Proveedor', x='Total', text='Total',
        orientation='h', height=400,
        color='Total',
        color_continuous_scale=['#2ECC71', '#0A2540'],
    )
    fig.update_traces(
        texttemplate='$%{x:,.0f}', textposition='outside',
        hovertemplate='<b>%{y}</b><br>Total: $%{x:,.2f}<br>Facturas: %{customdata[0]}<extra></extra>',
        customdata=df[['Facturas']]
    )
    fig.update_layout(
        xaxis=dict(tickformat='$,.0f', gridcolor='rgba(0,0,0,0.05)'),
        yaxis=dict(title='', autorange='reversed'),
        coloraxis_showscale=False,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=60, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def grafico_tarifa_progresiva():
    fig = go.Figure()
    tarifa = TARIFA_ISR_2026

    colores_tramos = [
        '#2ECC71', '#27AE60', '#F1C40F', '#F39C12',
        '#E67E22', '#E74C3C', '#C0392B', '#9B59B6',
        '#8E44AD', '#2980B9', '#1A3A5C'
    ]

    labels = []
    cuotas = []
    for i, (li, ls, cf, pct) in enumerate(tarifa):
        ls_label = f"${ls:,.0f}" if ls != float('inf') else "∞"
        labels.append(f"{i+1}°: ${li:,.0f} - {ls_label}")
        cuotas.append(cf)

    fig.add_trace(go.Bar(
        y=labels, x=cuotas, orientation='h',
        marker_color=colores_tramos[:len(labels)],
        text=[f"${c:,.0f}" for c in cuotas],
        textposition='outside',
        hovertemplate='<b>%{y}</b><br>Cuota fija: $%{x:,.2f}<extra></extra>'
    ))

    porcentajes = [pct for _, _, _, pct in tarifa]
    for i, (li, ls, cf, pct) in enumerate(tarifa):
        pct_str = f"{pct:.2f}%"
        fig.add_annotation(
            x=cf + (max(cuotas) * 0.02), y=i,
            text=f"Tasa marginal: {pct_str}",
            showarrow=False, font=dict(size=10, color='#555'),
            xanchor='left',
        )

    fig.update_layout(
        height=450,
        xaxis=dict(title='Cuota Fija (MXN)', tickformat='$,.0f',
                    gridcolor='rgba(0,0,0,0.05)'),
        yaxis=dict(title='', autorange='reversed'),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=160, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def sunburst_ingresos_cliente(info, key="sunburst"):
    df = info['top_clientes'].head(8)
    if df.empty:
        return

    otros = info['total_ingresos'] - df['Total'].sum()
    if otros > 0:
        otros_row = pd.DataFrame([{'Cliente': 'Otros', 'Total': otros, 'Facturas': 0, 'Promedio': 0}])
        df = pd.concat([df, otros_row], ignore_index=True)

    fig = px.sunburst(
        df, path=['Cliente'], values='Total',
        color='Total', color_continuous_scale=['#E8D5A3', COLOR_SECONDARY, COLOR_PRIMARY],
        height=380,
    )
    fig.update_traces(
        hovertemplate='<b>%{label}</b><br>Total: $%{value:,.2f}<extra></extra>'
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, key=key, use_container_width=True)


def donut_gastos(info):
    if info['total_no_deducible'] > 0:
        labels = ['Deducibles', 'Posibles No Deducibles']
        values = [info['total_gastos'] - info['total_no_deducible'], info['total_no_deducible']]
        colors = ['#0A2540', '#E74C3C']
    else:
        labels = ['Gastos Deducibles']
        values = [info['total_gastos']]
        colors = ['#0A2540']

    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.6,
        marker_colors=colors,
        textinfo='label+percent',
        textfont=dict(size=13),
        hovertemplate='<b>%{label}</b><br>$%{value:,.2f} (%{percent})<extra></extra>',
    )])
    fig.update_layout(
        height=380,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def tabla_no_deducibles(info):
    df = info['no_deducibles']
    if df.empty:
        st.info("No se detectaron gastos potencialmente no deducibles.")
        return

    cols = ['UUID', 'RFC Emisor', 'Subtotal', 'Conceptos']
    mostrar = df[cols].copy() if all(c in df.columns for c in cols) else df
    mostrar['Subtotal'] = mostrar['Subtotal'].apply(lambda x: f"${x:,.2f}")

    st.dataframe(
        mostrar,
        use_container_width=True,
        hide_index=True,
        column_config={
            'UUID': st.column_config.TextColumn('UUID', width=200),
            'RFC Emisor': st.column_config.TextColumn('Proveedor', width=130),
            'Subtotal': st.column_config.TextColumn('Monto', width=100),
            'Conceptos': st.column_config.TextColumn('Concepto', width=400),
        }
    )


def fiscal_health_gauge(info):
    util = info['utilidad_fiscal']
    ingresos = info['total_ingresos']
    margen = info['margen_neto']

    carga = info['carga_total']
    salud = 100 - carga - (abs(margen - 15) * 0.5)
    salud = max(0, min(100, salud))

    color = '#E74C3C' if salud < 40 else '#F39C12' if salud < 65 else '#2ECC71'

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=salud,
        number=dict(suffix="%", font=dict(size=28, color=COLOR_PRIMARY)),
        title=dict(text="Índice de Salud Fiscal", font=dict(size=14, color=COLOR_PRIMARY)),
        delta=dict(
            reference=50,
            valueformat=".0f",
            increasing=dict(color="#2ECC71"),
            decreasing=dict(color="#E74C3C"),
        ),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor=COLOR_PRIMARY),
            bar=dict(color=color, thickness=0.4),
            bgcolor='white',
            borderwidth=2, bordercolor='rgba(0,0,0,0.05)',
            steps=[
                dict(range=[0, 30], color='rgba(231,76,60,0.15)'),
                dict(range=[30, 60], color='rgba(243,156,18,0.15)'),
                dict(range=[60, 100], color='rgba(46,204,113,0.15)'),
            ],
            threshold=dict(
                line=dict(color=COLOR_SECONDARY, width=4),
                thickness=0.75, value=salud,
            ),
        )
    ))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)


def tabla_mensual_detalle(info):
    df = info['datos_mensuales'].copy()
    if df.empty:
        return

    cols_mostrar = ['Ingresos Gravables', 'Gastos Deducibles',
                    'ISR Provisional', 'IVA a Pagar', 'Posibles No Deducibles']
    cols_existentes = [c for c in cols_mostrar if c in df.columns]

    mostrar = df[cols_existentes].copy()
    for c in mostrar.columns:
        mostrar[c] = mostrar[c].apply(lambda x: f"${x:,.2f}")

    st.dataframe(mostrar, use_container_width=True)


def mostrar_recomendaciones(info):
    st.markdown("### 💡 Recomendaciones Fiscales Estratégicas")

    util = info['utilidad_fiscal']
    ingresos = info['total_ingresos']
    margen = info['margen_neto']
    isr_causado = info['resumen_anual'].get('ISR Causado (30% PM)', 0)
    isr_pagado = info['total_isr_provisional']
    no_ded = info['total_no_deducible']

    recomendaciones = []

    if isr_pagado > isr_causado:
        dif = isr_pagado - isr_causado
        recomendaciones.append((
            "✅ Saldo a Favor en ISR",
            f"Los pagos provisionales ($ {isr_pagado:,.0f}) exceden el ISR causado "
            f"($ {isr_causado:,.0f}) por **$ {dif:,.0f}**. Puedes solicitar devolución "
            "o compensación contra el IVA u otros impuestos."
        ))

    if no_ded > 0:
        pct_no_ded = (no_ded / info['total_gastos'] * 100) if info['total_gastos'] > 0 else 0
        recomendaciones.append((
            "⚠️ Gastos No Deducibles",
            f"Se identificaron **$ {no_ded:,.0f}** ({pct_no_ded:.1f}% del total de gastos) en "
            f"conceptos potencialmente no deducibles. Si se confirman como no deducibles, "
            f"la utilidad fiscal real sería mayor. Revisa los conceptos detectados y "
            "asegúrate de contar con la documentación de los mismos."
        ))

    if margen < 5:
        recomendaciones.append((
            "🔴 Margen de Utilidad Reducido",
            f"El margen de utilidad es de solo **{margen:.1f}%**, lo que podría "
            f"llamar la atención del SAT (presunción de ingresos). Considera "
            f"revisar la deducción de gastos y el coeficiente de utilidad aplicado."
        ))
    elif margen > 25:
        recomendaciones.append((
            "🟡 Margen de Utilidad Elevado",
            f"El margen de utilidad es de **{margen:.1f}%**, lo que indica una alta "
            f"rentabilidad. Evalúa si conviene realizar inversiones o adquisiciones "
            "antes del cierre del ejercicio para optimizar la carga fiscal."
        ))

    if info['carga_isr'] < 6:
        recomendaciones.append((
            "💡 Carga ISR Baja",
            f"La carga efectiva de ISR es de solo **{info['carga_isr']:.1f}%** sobre ingresos, "
            f"debido al coeficiente de utilidad ({COEF_UTILIDAD*100:.2f}%) y la tasa fija "
            f"del {TASA_ISR_PM*100:.0f}% para Personas Morales. Revisa que el coeficiente "
            f"esté correctamente calculado de la declaración 2025."
        ))

    clientes = info['clientes_50pct']
    if clientes <= 3:
        recomendaciones.append((
            "📊 Concentración de Clientes",
            f"Solo **{clientes} clientes** concentran más del 50% de los ingresos. "
            "Existe riesgo de dependencia. Considera diversificar tu base de clientes."
        ))

    recomendaciones.append((
        "📅 Planeación Fiscal 2027",
        "El coeficiente de utilidad para 2027 se calculará con la declaración anual de 2026. "
        "Monitorea tus ingresos y gastos mensuales para proyectar el coeficiente y "
        "evitar sorpresas en los pagos provisionales del siguiente ejercicio."
    ))

    for i, (titulo, texto) in enumerate(recomendaciones):
        st.markdown(f"""<div class="insight">
            <strong>{titulo}</strong><br>{texto}</div>""",
            unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div style="text-align:center;color:#999;font-size:0.85rem;">
    <em>Fundamento legal: LISR Arts. 9, 14 (Personas Morales) | Art. 152 (Personas Físicas, ref.)<br>
    LIVA Arts. 1, 4, 5 | RMF 2026 Anexo 8<br>
    Análisis generado con base en la información de los CFDIs procesados.</em>
    </div>
    """, unsafe_allow_html=True)


def resumen_anual_tabla(info):
    res = info['resumen_anual']
    if not res:
        return

    df = pd.DataFrame([
        ('📈 Ingresos Brutos', f"${res.get('Ingresos', 0):,.2f}"),
        ('📉 Gastos Deducibles', f"${res.get('Gastos', 0):,.2f}"),
        ('⚠️ Posibles No Deducibles', f"${res.get('Gastos No Deducibles Detectados', 0):,.2f}"),
        ('💰 Utilidad Fiscal', f"${res.get('Utilidad Fiscal', 0):,.2f}"),
        ('🏛️ ISR Causado (30% PM)', f"${res.get('ISR Causado (30% PM)', 0):,.2f}"),
        ('🏛️ ISR Pagado (Provisional)', f"${res.get('ISR Pagado (Provisional)', 0):,.2f}"),
        ('🏛️ ISR Anual a Pagar', f"${res.get('ISR Anual a Pagar', 0):,.2f}"),
        ('🧾 IVA Anual a Pagar', f"${res.get('IVA Anual a Pagar', 0):,.2f}"),
    ], columns=['Concepto', 'Monto'])

    st.table(df.style.set_properties(
        **{'text-align': 'left', 'font-size': '0.85rem'}
    ).set_table_styles([
        dict(selector='th', props=[('text-align', 'left'), ('font-weight', '600'),
             ('color', COLOR_PRIMARY)]),
    ]))


# ─── APLICACIÓN PRINCIPAL ────────────────────────────────────────────────

def main():
    sidebar_info(RFC, NOMBRE_EMPRESA)

    with st.spinner("📂 Procesando 438 comprobantes fiscales..."):
        df_emit, df_recib = procesar_todo()
        info = analisis_detallado(df_emit, df_recib)

    st.session_state['datos_mensuales'] = info.get('datos_mensuales', pd.DataFrame())
    st.session_state['resumen_anual'] = info.get('resumen_anual', {})

    # ── HEADER ──
    c_logo, c_title = st.columns([0.08, 1])
    with c_logo:
        st.markdown(f"""<div style="background:{COLOR_PRIMARY};width:50px;height:50px;
            border-radius:12px;display:flex;align-items:center;justify-content:center;">
            <span style="color:white;font-weight:800;font-size:1.3rem;">BM</span></div>""",
            unsafe_allow_html=True)
    with c_title:
        st.markdown(f'<div class="main-header">Dashboard Fiscal {EJERCICIO}</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="main-sub">{NOMBRE_EMPRESA} · RFC {RFC} · '
                    f'{REGIMEN} · {ACTIVIDAD}</div>',
                    unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── TABS ──
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Resumen Ejecutivo",
        "📈 Ingresos",
        "📉 Gastos",
        "🏛️ Impuestos",
        "💡 Recomendaciones"
    ])

    # ── TAB 1: Resumen Ejecutivo ──
    with tab1:
        metricas_principales(info)

        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns([3, 2])

        with col1:
            st.markdown(f'<div class="card"><div class="card-title">📊 Ingresos vs Gastos</div>',
                        unsafe_allow_html=True)
            grafico_ingresos_gastos(info, key="ig_resumen")
            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown(f'<div class="card"><div class="card-title">🏥 Salud Fiscal</div>',
                        unsafe_allow_html=True)
            fiscal_health_gauge(info)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f'<div class="card"><div class="card-title">📋 Resumen Anual</div>',
                        unsafe_allow_html=True)
            resumen_anual_tabla(info)
            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown(f'<div class="card"><div class="card-title">💰 Distribución de Ingresos</div>',
                        unsafe_allow_html=True)
            sunburst_ingresos_cliente(info, key="sunburst_resumen")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f'<div class="card"><div class="card-title">📅 Detalle Mensual</div>',
                    unsafe_allow_html=True)
        tabla_mensual_detalle(info)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── TAB 2: Ingresos ──
    with tab2:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f'<div class="card"><div class="card-title">🏆 Top 10 Clientes</div>',
                        unsafe_allow_html=True)
            top_clientes_chart(info)
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="card"><div class="card-title">📊 Por Cliente</div>',
                        unsafe_allow_html=True)
            sunburst_ingresos_cliente(info, key="sunburst_ingresos")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f'<div class="card"><div class="card-title">📈 Tendencia Mensual de Ingresos</div>',
                    unsafe_allow_html=True)
        grafico_ingresos_gastos(info, key="ig_tendencia")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if not info['top_clientes'].empty:
            st.markdown(f'<div class="card"><div class="card-title">📋 Detalle de Clientes</div>',
                        unsafe_allow_html=True)
            df = info['top_clientes'].copy()
            df['Total'] = df['Total'].apply(lambda x: f"${x:,.2f}")
            df['Promedio'] = df['Promedio'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ── TAB 3: Gastos ──
    with tab3:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f'<div class="card"><div class="card-title">🏆 Top 10 Proveedores</div>',
                        unsafe_allow_html=True)
            top_proveedores_chart(info)
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="card"><div class="card-title">🍩 Composición Gastos</div>',
                        unsafe_allow_html=True)
            donut_gastos(info)
            st.markdown('</div>', unsafe_allow_html=True)

        if info['total_no_deducible'] > 0:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""<div class="card">
                <div class="card-title" style="color:{COLOR_DANGER};">⚠️ Gastos No Deducibles Detectados</div>""",
                        unsafe_allow_html=True)
            col1, col2 = st.columns([1, 2])
            with col1:
                st.metric("Monto Identificado",
                          f"${info['total_no_deducible']:,.2f}",
                          f"{info['total_no_deducible']/info['total_gastos']*100:.1f}% del total")
            with col2:
                tabla_no_deducibles(info)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if not info['top_proveedores'].empty:
            st.markdown(f'<div class="card"><div class="card-title">📋 Detalle de Proveedores</div>',
                        unsafe_allow_html=True)
            df = info['top_proveedores'].copy()
            df['Total'] = df['Total'].apply(lambda x: f"${x:,.2f}")
            df['Promedio'] = df['Promedio'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ── TAB 4: Impuestos ──
    with tab4:
        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown(f'<div class="card"><div class="card-title">📊 ISR e IVA Mensual</div>',
                        unsafe_allow_html=True)
            grafico_impuestos_mensuales(info)
            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown(f'<div class="card"><div class="card-title">🏛️ ISR Causado vs Pagado</div>',
                        unsafe_allow_html=True)
            isr_c = info['resumen_anual'].get('ISR Causado (30% PM)', 0)
            isr_p = info['total_isr_provisional']

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=['ISR Causado', 'ISR Pagado'],
                y=[isr_c, isr_p],
                text=[f"${isr_c:,.0f}", f"${isr_p:,.0f}"],
                textposition='outside',
                marker_color=['#C8A951', '#0A2540'],
                hovertemplate='%{x}: $%{y:,.2f}<extra></extra>',
            ))
            fig.update_layout(
                height=300,
                yaxis=dict(tickformat='$,.0f', gridcolor='rgba(0,0,0,0.05)'),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            col1_1, col1_2 = st.columns(2)

            with col1_1:
                st.markdown(f"""<div class="card"><div class="card-title">📋 Persona Moral</div>
                    <div style="font-size:0.85rem;color:#333;line-height:1.5;">
                    <p><strong>Tasa ISR:</strong> {TASA_ISR_PM*100:.0f}% fija (Art. 9 LISR)<br>
                    <strong>IVA:</strong> {TAXA_IVA*100:.0f}%<br>
                    <strong>Régimen:</strong> General de Ley PM<br>
                    <strong>Coef. Utilidad:</strong> {COEF_UTILIDAD*100:.2f}%</p>
                    <div style="background:#F0F4F8;padding:0.8rem;border-radius:8px;
                         font-size:0.8rem;margin-top:0.5rem;">
                    Los pagos provisionales se calculan con el coeficiente de utilidad
                    del ejercicio anterior aplicado a los ingresos del período (Art. 14 LISR).
                    El ISR anual se determina sobre la utilidad fiscal real.
                    </div></div>""", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            with col1_2:
                st.markdown(f"""<div class="card"><div class="card-title">📅 Declaración 2025
                    <span style="font-weight:400;font-size:0.7rem;color:#999;margin-left:0.5rem;">
                    (Ejercicio anterior)</span></div>
                    <div style="font-size:0.85rem;color:#333;line-height:1.8;">
                    <strong>ISR Causado:</strong> $ {DECLARACION_2025['isr_causado']:,.2f}<br>
                    <strong>Presentación:</strong> {DECLARACION_2025['presentacion']}<br>
                    <strong>Coeficiente derivado:</strong> {COEF_UTILIDAD*100:.2f}%<br>
                    </div>
                    <div style="background:#F0F4F8;padding:0.8rem;border-radius:8px;
                         font-size:0.8rem;margin-top:0.5rem;color:#666;">
                    Coeficiente = Utilidad Fiscal ÷ Ingresos Nominales del ejercicio 2025.
                    Este coeficiente se usa para los pagos provisionales de {EJERCICIO}.
                    </div>""", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown(f'<div class="card"><div class="card-title">🧾 Resumen de Impuestos</div>',
                        unsafe_allow_html=True)
            resumen_anual_tabla(info)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("#### 📈 Carga Fiscal Efectiva")
            st.markdown(f"""
            <div style="display:flex;gap:1rem;flex-wrap:wrap;">
                <div style="flex:1;min-width:120px;background:#F0F4F8;padding:1rem;
                     border-radius:10px;text-align:center;">
                    <div style="font-size:0.7rem;color:#666;text-transform:uppercase;
                         letter-spacing:1px;">ISR Efectivo</div>
                    <div style="font-size:1.5rem;font-weight:700;color:{COLOR_PRIMARY};">
                    {info['carga_isr']:.1f}%</div>
                </div>
                <div style="flex:1;min-width:120px;background:#F0F4F8;padding:1rem;
                     border-radius:10px;text-align:center;">
                    <div style="font-size:0.7rem;color:#666;text-transform:uppercase;
                         letter-spacing:1px;">IVA Efectivo</div>
                    <div style="font-size:1.5rem;font-weight:700;color:{COLOR_DANGER};">
                    {info['carga_iva']:.1f}%</div>
                </div>
                <div style="flex:1;min-width:120px;background:{COLOR_PRIMARY};padding:1rem;
                     border-radius:10px;text-align:center;">
                    <div style="font-size:0.7rem;color:rgba(255,255,255,0.7);text-transform:uppercase;
                         letter-spacing:1px;">Carga Total</div>
                    <div style="font-size:1.5rem;font-weight:700;color:white;">
                    {info['carga_total']:.1f}%</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            isr_2025 = DECLARACION_2025['isr_causado']
            st.markdown(f"""<div style="background:#FFFEF5;border-left:4px solid {COLOR_SECONDARY};
                padding:0.8rem 1rem;border-radius:0 8px 8px 0;font-size:0.85rem;">
                <strong>🔁 Comparativa 2025 → 2026</strong><br>
                ISR 2025: $ {isr_2025:,.0f} · ISR 2026 (proyectado enero-mayo): $ {isr_c:,.0f}
            </div>""", unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

    # ── TAB 5: Recomendaciones ──
    with tab5:
        st.markdown(f"""<div class="card">
            <div class="card-title">💡 Análisis y Recomendaciones Fiscales</div>""",
                    unsafe_allow_html=True)
        mostrar_recomendaciones(info)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── FOOTER ──
    st.markdown(f"""
    <div class="footer">
        <strong>{NOMBRE_EMPRESA}</strong> · RFC {RFC} · {DOMICILIO}<br>
        Dashboard Fiscal {EJERCICIO} · {len(df_emit) + len(df_recib)} CFDIs procesados ·
        Actividad: {ACTIVIDAD}<br>
        <em>Este análisis tiene fines informativos. Consulte a su contador para
        la declaración fiscal oficial.</em>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()

"""AURA chart helpers: use dated EOD positions, never invent missing P/L or percentage returns."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def _valid_table(table: pd.DataFrame) -> pd.DataFrame:
    required = ('Ngày', 'Lãi/lỗ lũy kế (VND)', 'Thay đổi P/L ngày (VND)')
    if not isinstance(table, pd.DataFrame) or any(c not in table.columns for c in required):
        raise ValueError('Bảng lãi/lỗ chưa có đủ ba cột Ngày, lũy kế và thay đổi theo ngày.')
    t = table.copy()
    t['Ngày'] = pd.to_datetime(t['Ngày'], errors='coerce').dt.normalize()
    t = t.dropna(subset=['Ngày']).sort_values('Ngày').drop_duplicates('Ngày', keep='last')
    for name in required[1:]:
        t[name] = pd.to_numeric(t[name], errors='coerce')
    if t.empty:
        raise ValueError('Không còn ngày hợp lệ để vẽ biểu đồ.')
    return t


def _date_axis(fig: go.Figure, dates: pd.Series) -> None:
    first, last = dates.iloc[0], dates.iloc[-1]
    days = max(1, int((last - first).days))
    padding = pd.Timedelta(days=max(1, min(10, int(days * .03) + 1)))
    fig.update_xaxes(
        type='date',
        range=[(first-padding).to_pydatetime(), (last+padding).to_pydatetime()],
        tickformat='%d/%m/%Y', hoverformat='%d/%m/%Y',
        showgrid=True, gridcolor='#ECE7F6',
        tickmode='array' if len(dates) <= 12 else 'auto',
        tickvals=[v.to_pydatetime() for v in dates] if len(dates) <= 12 else None,
        ticktext=[v.strftime('%d/%m/%Y') for v in dates] if len(dates) <= 12 else None,
    )


def build_portfolio_line_figures(table: pd.DataFrame) -> tuple[go.Figure, go.Figure, int]:
    """Return cumulative & daily P/L line charts, number of distinct dated observations.

    The numbers are VND P/L (NOT time-weighted return %). On a single day only
    markers are used so Plotly cannot fabricate a line nor microsecond ticks.
    """
    t = _valid_table(table)
    x = t['Ngày']
    n = len(t)
    mode = 'lines+markers' if n >= 2 else 'markers'

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=t['Lãi/lỗ lũy kế (VND)'], name='Lãi/lỗ lũy kế (VND)',
        mode=mode, connectgaps=False,
        line={'color': '#7136EB', 'width': 3},
        marker={'color': '#7136EB', 'size': 9},
        hovertemplate='%{x|%d/%m/%Y}<br>Lũy kế: %{y:,.0f} đ<extra></extra>',
    ))
    fig.add_hline(y=0, line_color='#72648C', line_dash='dot', opacity=.65)
    fig.update_layout(
        title={'text': 'Lãi/lỗ lũy kế theo ngày', 'font': {'size': 16}},
        height=365, template='plotly_white',
        margin={'l': 10, 'r': 18, 't': 52, 'b': 12},
        paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF',
        yaxis_title='VND', xaxis_title=None, hovermode='x unified',
        showlegend=False,
    )
    _date_axis(fig, x)

    daily = t['Thay đổi P/L ngày (VND)']
    dfig = go.Figure()
    dfig.add_trace(go.Scatter(
        x=x, y=daily, name='Thay đổi P/L theo ngày (VND)',
        mode=mode, connectgaps=False,
        line={'color': '#149D8F', 'width': 2.7},
        marker={'size': 9, 'color': ['#149D8F' if pd.notna(v) and v >= 0 else '#E54D86'
                                        for v in daily]},
        hovertemplate='%{x|%d/%m/%Y}<br>Thay đổi ngày: %{y:,.0f} đ<extra></extra>',
    ))
    dfig.add_hline(y=0, line_color='#72648C', line_dash='dot', opacity=.65)
    dfig.update_layout(
        title={'text': 'Thay đổi lãi/lỗ từng ngày (đường)', 'font': {'size': 16}},
        height=320, template='plotly_white',
        margin={'l': 10, 'r': 18, 't': 52, 'b': 12},
        paper_bgcolor='#FFFFFF', plot_bgcolor='#FFFFFF',
        yaxis_title='VND', xaxis_title=None, hovermode='x unified',
        showlegend=False,
    )
    _date_axis(dfig, x)
    return fig, dfig, n

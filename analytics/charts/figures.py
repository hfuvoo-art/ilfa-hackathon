"""Функции Plotly для встраивания в интерфейс."""

from collections import defaultdict

import plotly.graph_objects as go
from plotly.subplots import make_subplots


BLUE = "#175b8a"
TEAL = "#087e79"
GOLD = "#b96d28"


def _style(fig, title, takeaway):
    fig.update_layout(
        template="plotly_white", title_text=title,
        font=dict(family="Segoe UI, Arial, sans-serif", color="#203246", size=14),
        margin=dict(l=64, r=46, t=75, b=100),
        legend=dict(orientation="h", y=1.08, x=0),
        separators=", ",
    )
    fig.add_annotation(
        text=takeaway, xref="paper", yref="paper", x=0, y=-0.24,
        xanchor="left", align="left", showarrow=False,
    )
    return fig


def segment_chart(rows):
    rows = sorted(rows, key=lambda row: row["n_patients"])
    fig = go.Figure(go.Bar(
        y=[row["segment"] or "Сегмент неизвестен" for row in rows],
        x=[row["n_patients"] for row in rows], orientation="h", marker_color=BLUE,
        hovertemplate="%{y}<br>Пациентов: %{x}<extra></extra>",
    ))
    fig.update_xaxes(title_text="Пациенты", rangemode="tozero")
    fig.update_yaxes(automargin=True)
    return _style(fig, "Распределение пациентов по сегментам", "Размер сегмента помогает выбрать охват кампании.")


def pareto_chart(patients, shares, hit):
    fig = go.Figure(go.Scatter(
        x=patients, y=shares, mode="lines", line_color=BLUE, name="Накопленная выручка",
        hovertemplate="Пациенты: %{x:.1%}<br>Выручка: %{y:.1%}<extra></extra>",
    ))
    if hit is not None:
        fig.add_hline(y=0.8, line_dash="dash", line_color=GOLD)
        fig.add_trace(go.Scatter(
            x=[patients[hit]], y=[shares[hit]], name="Порог 80%", mode="markers",
            marker=dict(size=11, color=GOLD),
            hovertemplate="%{x:.1%} пациентов дают %{y:.1%} выручки<extra></extra>",
        ))
    if not patients:
        fig.add_annotation(text="Для расчёта нужна положительная общая выручка",
                           showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_xaxes(title_text="Доля пациентов", tickformat=".0%", range=[0, 1])
    fig.update_yaxes(title_text="Накопленная доля выручки", tickformat=".0%")
    return _style(fig, "Парето по выручке", "Кривая показывает, насколько выручка сосредоточена у небольшой группы.")


def ltv_chart(rows):
    segments = [row["segment"] or "Сегмент неизвестен" for row in rows]
    fig = go.Figure([
        go.Bar(x=segments, y=[row["avg_ltv_hist"] for row in rows], name="Исторический", marker_color=BLUE),
        go.Bar(x=segments, y=[row["avg_ltv_pred"] for row in rows], name="Прогноз на 12 месяцев", marker_color=TEAL),
    ])
    fig.update_layout(barmode="group")
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(title_text="Средний LTV, ₽", rangemode="tozero")
    return _style(fig, "Исторический и прогнозный LTV", "Сравнение помогает выбрать сегменты для проверки гипотез удержания.")


def top_services_chart(rows, limit=10):
    ranked = sorted(rows, key=lambda row: row["revenue"], reverse=True)[:limit]
    labels = [f'{row["service_name"] or "Неизвестная услуга"} · {row["category"] or "Без категории"}'
              for row in reversed(ranked)]
    fig = go.Figure(go.Bar(
        y=labels, x=[row["revenue"] for row in reversed(ranked)], orientation="h", marker_color=TEAL,
        hovertemplate="%{y}<br>Выручка: %{x:,.0f} ₽<extra></extra>",
    ))
    fig.update_xaxes(title_text="Выручка, ₽", rangemode="tozero")
    fig.update_yaxes(automargin=True)
    return _style(fig, "Топ услуг по выручке", "Высокая выручка помогает выбрать услуги для проверки спроса.")


def retention_chart(rows):
    cohorts = sorted({row["cohort"] for row in rows})
    windows = sorted({row["window"] for row in rows})
    cells = {(row["cohort"], row["window"]): row for row in rows}
    shares, counts = [], []
    for cohort in cohorts:
        cohort_rows = [cells[cohort, window] for window in windows]
        shares.append([row["share"] for row in cohort_rows])
        counts.append([[row["n_returned"], row["n_patients"]] for row in cohort_rows])
    fig = go.Figure(go.Heatmap(
        x=[f"{window} дней" for window in windows], y=cohorts, z=shares, customdata=counts,
        zmin=0, zmax=1, colorscale="Blues", colorbar=dict(tickformat=".0%"),
        hoverongaps=False, texttemplate="%{z:.0%}",
        hovertemplate="%{y} · %{x}<br>Повтор: %{z:.1%} (%{customdata[0]} из %{customdata[1]})<extra></extra>",
    ))
    fig.update_yaxes(title_text="Месяц первого визита", autorange="reversed")
    return _style(fig, "Удержание по когортам первого визита", "Пустые ячейки обозначают незавершённые окна наблюдения.")


def transition_chart(rows):
    categories = sorted({row[field] for row in rows for field in ("from_category", "to_category")})
    cells = {(row["from_category"], row["to_category"]): row for row in rows}
    outgoing = {row["from_category"] for row in rows}
    shares, counts = [], []
    for source in categories:
        source_cells = [cells.get((source, target)) for target in categories]
        shares.append([row["transition_share"] if row else (0 if source in outgoing else None) for row in source_cells])
        counts.append([[row["n_transitions"], row["n_patients"]] if row else [0, 0] for row in source_cells])
    fig = go.Figure(go.Heatmap(
        x=categories, y=categories, z=shares, customdata=counts, zmin=0, zmax=1,
        colorscale="Teal", colorbar=dict(tickformat=".0%"), hoverongaps=False, texttemplate="%{z:.0%}",
        hovertemplate="%{y} → %{x}<br>Доля: %{z:.1%}<br>Пар: %{customdata[0]}"
                      "<br>Пациентов: %{customdata[1]}<extra></extra>",
    ))
    fig.update_xaxes(title_text="Следующий визит", automargin=True)
    fig.update_yaxes(title_text="Предыдущий визит", autorange="reversed", automargin=True)
    return _style(fig, "Переходы между категориями", "Матрица помогает выбрать пары услуг для проверки командой offers.")


def monthly_chart(rows):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    months = [month for month, _, _ in rows]
    fig.add_trace(go.Bar(x=months, y=[count for _, count, _ in rows], name="Визиты", marker_color=BLUE),
                  secondary_y=True)
    fig.add_trace(go.Scatter(x=months, y=[revenue for _, _, revenue in rows], name="Выручка",
                            mode="lines+markers", line_color=GOLD), secondary_y=False)
    fig.update_xaxes(title_text="Месяц", tickformat="%m.%Y")
    fig.update_yaxes(title_text="Выручка, ₽", secondary_y=False, zeroline=True)
    fig.update_yaxes(title_text="Визиты", secondary_y=True, rangemode="tozero", showgrid=False)
    return _style(fig, "Выручка и визиты по месяцам", "Сопоставление рядов помогает заметить месяцы, где меняется средний чек.")


def weekday_chart(rows):
    fig = go.Figure(go.Bar(
        x=[day for day, _, _ in rows], y=[count for _, count, _ in rows],
        customdata=[revenue for _, _, revenue in rows], marker_color=TEAL,
        hovertemplate="%{x}<br>Визитов: %{y}<br>Выручка: %{customdata:,.0f} ₽<extra></extra>",
    ))
    fig.update_yaxes(title_text="Визиты", rangemode="tozero")
    return _style(fig, "Активность по дням недели", "По будням и выходным можно проверить, в какие дни есть свободные окна.")

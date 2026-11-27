"""Демонстрация всех графиков на вымышленных данных SQLite."""

from argparse import ArgumentParser
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from analytics.demo_data import create_demo_db
from analytics.segments import compute_segments

from . import load_chart_data, render_charts, return_scenario


DEMO_ASSUMPTIONS = {
    "contact_share": 0.8, "baseline_rate": 0.1, "campaign_rate": 0.2, "visits_per_return": 1,
}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("analytics/charts/demo.html"))
    args = parser.parse_args()

    engine = create_engine("sqlite://", creator=lambda: create_demo_db(extended=True), poolclass=StaticPool)
    try:
        compute_segments(engine)
        data = load_chart_data(engine)
    finally:
        engine.dispose()

    figures = render_charts(data)
    content = "\n".join(
        fig.to_html(full_html=False, include_plotlyjs=index == 0, div_id=f"chart-{name}",
                    config={"displaylogo": False})
        for index, (name, fig) in enumerate(figures.items())
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"""<!doctype html>
<html lang="ru">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ильфа · демонстрация аналитики</title>
<style>
body {{ max-width: 1160px; margin: 28px auto; padding: 0 16px; font: 16px Segoe UI, Arial, sans-serif; }}
.plotly-graph-div {{ margin-bottom: 18px; }}
</style>
<h1>Визиты, выручка и удержание</h1>
<p>Все данные вымышлены. Графики показывают работу расчётов.</p>
{content}
</html>
""", encoding="utf-8")
    print(f"Сохранено графиков: {len(figures)}. Файл: {args.output}")
    for row in return_scenario(data["patients"], **DEMO_ASSUMPTIONS):
        amount = row["incremental_revenue"]
        formatted = f"{amount:.2f} ₽" if amount is not None else "чек неизвестен"
        print(f'{row["segment"]}: {row["n_patients"]} пациентов, дополнительная выручка {formatted}.')


if __name__ == "__main__":
    main()

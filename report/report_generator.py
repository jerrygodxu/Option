import datetime as dt
from typing import List, Optional

from strategy.premium_strategy import PremiumOpportunity, WatchlistCandidate


def generate_markdown_report(
    opportunities: List[PremiumOpportunity],
    run_date: dt.date,
    watchlist: Optional[List[WatchlistCandidate]] = None,
) -> str:
    title = f"Option Premium Selling Opportunities - {run_date.isoformat()}"
    lines: list[str] = [f"## {title}", ""]

    if watchlist is None:
        watchlist = []

    if not opportunities:
        lines.append("No qualifying premium-selling opportunities were found today.")
        if watchlist:
            lines.append("")
            lines.append("### Watchlist")
            lines.append("")
            lines.append(
                "| Rank | Ticker | Direction | Contract | Premium | Signal | Note |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            for rank, candidate in enumerate(watchlist, start=1):
                c = candidate.enriched_option.contract
                delta_str = (
                    f"{candidate.enriched_option.delta:.3f}"
                    if candidate.enriched_option.delta is not None
                    else "N/A"
                )
                contract = (
                    f"{c.expiration.isoformat()} / {c.strike:.2f} / DTE {candidate.enriched_option.dte}"
                )
                premium = (
                    f"{c.mid:.2f} / spr {c.spread:.2f} ({c.spread_pct * 100:.1f}%)"
                    if c.spread == c.spread and c.spread_pct == c.spread_pct
                    else f"{c.mid:.2f}"
                )
                signal = (
                    f"px {candidate.underlying_price:.2f} / "
                    f"RSI {candidate.rsi:.1f} / delta {delta_str} / "
                    f"setup {candidate.setup_score:.2f}"
                )
                lines.append(
                    f"| {rank} | {candidate.ticker} | {candidate.direction.upper()} | "
                    f"{contract} | {premium} | {signal} | {candidate.note} |"
                )
        return "\n".join(lines)

    def fmt_pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    def fmt_earnings(opp: PremiumOpportunity) -> str:
        if opp.days_to_earnings is None or opp.earnings_date is None:
            return "-"
        return f"{opp.days_to_earnings}d ({opp.earnings_date.isoformat()})"

    def fmt_management(opp: PremiumOpportunity) -> str:
        return (
            f"TP {opp.take_profit_pct * 100:.0f}% / "
            f"roll <= {opp.roll_dte_threshold} DTE"
        )

    ordered = sorted(opportunities, key=lambda o: o.score, reverse=True)
    call_count = sum(1 for opp in ordered if opp.direction == "call")
    put_count = sum(1 for opp in ordered if opp.direction == "put")
    lines.append(
        f"Total: **{len(ordered)}** candidates | CALL: **{call_count}** | PUT: **{put_count}**"
    )
    lines.append("")

    def render_section(direction: str) -> None:
        section = [opp for opp in ordered if opp.direction == direction]
        if not section:
            return

        lines.append(f"### {direction.upper()}")
        lines.append("")
        lines.append(
            "| Rank | Ticker | Contract | Style | OTM Buffer | Premium | Return | Liquidity | Signal | Mgmt | Score |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

        for rank, opp in enumerate(section, start=1):
            c = opp.enriched_option.contract
            delta_str = (
                f"{opp.enriched_option.delta:.3f}"
                if opp.enriched_option.delta is not None
                else "N/A"
            )
            spread_str = f"{c.spread:.2f}" if c.spread == c.spread else "N/A"
            spread_pct_str = (
                f"{c.spread_pct * 100:.1f}%"
                if c.spread_pct == c.spread_pct
                else "N/A"
            )
            spot = opp.underlying_price
            if opp.direction == "call":
                otm_pct = (c.strike - spot) / spot if spot > 0 else 0.0
            else:
                otm_pct = (spot - c.strike) / spot if spot > 0 else 0.0
            contract = (
                f"{c.expiration.isoformat()} / {c.strike:.2f} / DTE {opp.enriched_option.dte}"
            )
            otm_buf = fmt_pct(max(otm_pct, 0.0))
            premium = f"{c.mid:.2f} / spr {spread_str} ({spread_pct_str})"
            style = f"{opp.strategy_style} / {opp.delta_band}"
            returns = (
                f"ann {fmt_pct(opp.enriched_option.annualized_return)} / "
                f"yield {fmt_pct(opp.enriched_option.premium_yield)}"
            )
            liquidity = f"OI {c.open_interest} / Vol {c.volume}"
            signal = (
                f"px {spot:.2f} / RSI {opp.rsi:.1f} / delta {delta_str} / "
                f"earn {fmt_earnings(opp)}"
            )
            lines.append(
                f"| {rank} | {opp.ticker} | {contract} | {style} | {otm_buf} | {premium} | "
                f"{returns} | {liquidity} | {signal} | {fmt_management(opp)} | {opp.score:.3f} |"
            )
        lines.append("")

    render_section("call")
    render_section("put")

    paired = {}
    for opp in ordered:
        key = (opp.ticker, opp.enriched_option.contract.expiration)
        paired.setdefault(key, {})[opp.direction] = opp

    strangles = [
        (key, value["call"], value["put"])
        for key, value in paired.items()
        if "call" in value and "put" in value
    ]
    if strangles:
        lines.append("### Strangle Ideas")
        lines.append("")
        lines.append(
            "| Ticker | Expiration | Call Strike | Put Strike | Combined Premium | Combined Score | Note |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for (ticker, expiration), call_opp, put_opp in sorted(
            strangles,
            key=lambda item: item[1].score + item[2].score,
            reverse=True,
        ):
            combined_premium = (
                call_opp.enriched_option.contract.mid + put_opp.enriched_option.contract.mid
            )
            note = (
                "earnings IV crush setup"
                if call_opp.strategy_style == "earnings" or put_opp.strategy_style == "earnings"
                else "candidate for covered strangle / short strangle review"
            )
            lines.append(
                f"| {ticker} | {expiration.isoformat()} | "
                f"{call_opp.enriched_option.contract.strike:.2f} | "
                f"{put_opp.enriched_option.contract.strike:.2f} | "
                f"{combined_premium:.2f} | {(call_opp.score + put_opp.score):.3f} | {note} |"
            )
        lines.append("")

    lines.append("")
    lines.append(
        "_Scoring: annualized return 22% + IV/RV 18% + absolute IV 15% + "
        "liquidity 15% + short-cycle efficiency 12% + OTM buffer 10% + "
        "weekly/earnings style bonus 5% + RSI extremeness 3%._"
    )

    return "\n".join(lines)

"""Tests for financial-analysis MCP tools."""

import json

from monarch_mcp_server.tools.financial import get_cashflow, get_net_worth


def _snapshots(count, start_balance=100.0):
    return [
        {"date": f"2020-{(i % 12) + 1:02d}-01", "balance": start_balance + i}
        for i in range(count)
    ]


class TestGetNetWorth:
    async def test_stats_and_snapshots_agree_when_under_the_cap(
        self, mock_monarch_client
    ):
        mock_monarch_client.get_aggregate_snapshots.return_value = {
            "aggregateSnapshots": _snapshots(10)
        }

        result = json.loads(await get_net_worth())

        assert result["snapshot_count"] == 10
        assert result["snapshots_truncated"] is False
        assert len(result["snapshots"]) == 10
        assert result["earliest_net_worth"] == 100.0
        assert result["current_net_worth"] == 109.0

    async def test_stats_cover_full_range_even_when_snapshots_are_truncated(
        self, mock_monarch_client
    ):
        """Regression test: stats must describe the whole requested range,
        and snapshots_truncated must say so, even though only the most
        recent 365 snapshots are included in `snapshots` itself."""
        mock_monarch_client.get_aggregate_snapshots.return_value = {
            "aggregateSnapshots": _snapshots(400)
        }

        result = json.loads(await get_net_worth(start_date="2015-01-01"))

        assert result["snapshot_count"] == 400
        assert result["snapshots_truncated"] is True
        assert len(result["snapshots"]) == 365
        # The earliest stat must reflect snapshot 0, not the earliest of the
        # truncated `snapshots` list (which would be snapshot 35).
        assert result["earliest_net_worth"] == 100.0
        assert result["current_net_worth"] == 499.0

    async def test_handles_api_error(self, mock_monarch_client):
        mock_monarch_client.get_aggregate_snapshots.side_effect = Exception("boom")
        result = await get_net_worth()
        assert "get_net_worth" in result


class TestGetCashflow:
    async def test_returns_cashflow_data(self):
        result = json.loads(await get_cashflow())
        assert result["cashflow"]["income"] == 5000.00
        assert result["cashflow"]["expenses"] == -3200.00

    async def test_passes_date_params(self, mock_monarch_client):
        await get_cashflow(start_date="2026-01-01", end_date="2026-01-31")
        mock_monarch_client.get_cashflow.assert_called_once_with(
            start_date="2026-01-01", end_date="2026-01-31"
        )

    async def test_handles_api_error(self, mock_monarch_client):
        mock_monarch_client.get_cashflow.side_effect = Exception("Cashflow error")
        result = await get_cashflow()
        assert "get_cashflow" in result

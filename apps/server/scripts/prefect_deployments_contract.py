"""Assert that Prefect Server contains exactly the active production deployments."""

import asyncio

from prefect.client.orchestration import get_client

EXPECTED_DEPLOYMENTS = {
    "chapter_extraction",
    "novel_ingestion_v3",
    "relationship_extraction",
    "story_aggregation",
}


def _assert_exact_deployments(registered: set[str]) -> None:
    missing = EXPECTED_DEPLOYMENTS.difference(registered)
    unexpected = registered.difference(EXPECTED_DEPLOYMENTS)
    if missing or unexpected:
        raise AssertionError(
            "Prefect deployment mismatch: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )


async def _check_deployments() -> None:
    async with get_client() as client:
        deployments = await client.read_deployments()

    registered = {deployment.name for deployment in deployments}
    _assert_exact_deployments(registered)

    print(f"Registered Prefect deployments: {sorted(EXPECTED_DEPLOYMENTS)}")


if __name__ == "__main__":
    asyncio.run(_check_deployments())

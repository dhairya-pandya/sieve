import pytest_asyncio

from sieve.near import NEAR, WASM_PATH, Near


@pytest_asyncio.fixture(scope="module")
async def chain():
    near = await Near.sandbox()
    yield near
    await near.close()


@pytest_asyncio.fixture(scope="module")
async def deployed(chain):
    """Sieve contract, an applicant and a Sputnik DAO whose council is the root account."""
    root = chain.root.account_id
    sieve = await chain.create_account(f"sieve.{root}", 30 * NEAR)
    await chain.deploy(sieve, WASM_PATH.read_bytes(), {"owner": root})
    applicant = await chain.create_account(f"alice.{root}", 20 * NEAR)
    dao = await chain.create_dao("dao", [root], sieve)
    return {"sieve": sieve, "applicant": applicant, "dao": dao, "root": root}

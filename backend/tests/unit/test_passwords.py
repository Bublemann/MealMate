from app.core.passwords import hash_password, verify_password


async def test_hash_and_verify() -> None:
    hashed = await hash_password("correct horse battery", rounds=4)
    assert hashed.startswith("$2b$04$")
    assert await verify_password("correct horse battery", hashed, rounds=4)
    assert not await verify_password("Correct horse battery", hashed, rounds=4)


async def test_verify_without_a_hash_does_the_work_and_fails() -> None:
    assert not await verify_password("anything at all", None, rounds=4)


async def test_verify_rejects_input_bcrypt_cannot_hash() -> None:
    hashed = await hash_password("x" * 72, rounds=4)
    assert await verify_password("x" * 72, hashed, rounds=4)
    assert not await verify_password("x" * 73, hashed, rounds=4)

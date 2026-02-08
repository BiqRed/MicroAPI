"""Example client using the auto-generated library."""

import asyncio
import sys
sys.path.insert(0, "..")

from shared.lib import users
from microapi.client.base import Connection
from microapi.transport.http import HTTPTransport


async def main():
    # Connect to the server
    transport = HTTPTransport(host="127.0.0.1", port=8080)
    client = transport.create_client()
    conn = Connection(client)

    async with conn:
        # 1. Unary call — just like calling a function
        print("=== Unary Call ===")
        user = await users.get_user(user_id=1)
        print(f"Got user: {user}")

        # 2. Server streaming — iterate over results
        print("\n=== Server Streaming ===")
        async for user in users.get_users():
            print(f"  Streamed user: {user}")

        # 3. Client streaming — send multiple messages
        print("\n=== Client Streaming ===")
        stream = users.add_users()
        await stream.send(username="adam", firstname="Adam", lastname="Smith", age=30)
        await stream.send(username="bob", firstname="Bob", lastname="Smith", age=40)
        await stream.end()
        print("  Done sending users")

        # 4. Bidirectional streaming
        print("\n=== Bidirectional Streaming ===")
        bidi = users.create_return_user()
        await bidi.send(username="charlie", firstname="Charlie", age=25)
        result = await bidi.next()
        print(f"  Created user: {result}")
        await bidi.end()


if __name__ == "__main__":
    asyncio.run(main())

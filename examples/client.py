from examples.lib import users


async def method_1():
    user = await users.get_user(user_id=1)
    print(user)


async def method_2():
    stream = users.get_users()
    async for user in stream:
        print(user)


async def method_3():
    stream = users.add_users()
    await stream.send(username='adam', firstname='Adam', lastname='Smith', age=30)
    await stream.send(username='bob', firstname='Bob', lastname='Smith', age=40)

    await stream.end()


async def method_4():
    stream = users.create_return_user()
    await stream.send(username='adam', firstname='Adam', lastname='Smith', age=30)

    user = await stream.next()
    print(user)

    await stream.end()

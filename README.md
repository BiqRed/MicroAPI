# MicroAPI

> **Note:** The project is under active development and not ready for production use yet.

MicroAPI bridges the gap between microservices, making remote calls feel like local function calls — clean, seamless, and intuitive.

---

## 📖 Table of Contents

1. [Key Features](#-key-features)
2. [Installation](#-installation)
3. [Quick Start](#-quick-start)
4. [Code Example](#-code-example)
5. [Project Structure](#-project-structure)
6. [Roadmap](#-roadmap)
7. [Contributing](#-contributing)
8. [License](#-license)

---

## 🔑 Key Features

* **Python-first**: all code is written in Python — simple, readable, and familiar.
* **Pydantic**: a fast, intuitive, and widely-used tool for data validation and typing.
* **Client Generation**: automatic generation of a fully typed client library with docstrings; CLI is just a helper tool.
* **Flexible Transports**:

  * Initial support: HTTP/2 (h2) and gRPC
  * Upcoming: Kafka, RabbitMQ, WebSocket, and others
  * Simple mechanism for adding custom transports
* **Middleware & Dependencies**: familiar FastAPI-like approach, with hot reload support
* **API Versioning**: clean support for maintaining and deprecating multiple API versions
* **Proto Files**: optional `.proto` generation for gRPC compatibility

---

## 🚀 Installation

```bash
# Using pip (from PyPI)
pip install microapi

# Or with Poetry
poetry add microapi

# Or with Pipenv
pipenv install microapi

# Or clone the repo (for development)
git clone https://github.com/your-org/microapi.git
cd microapi
poetry install
```

---

## ⚡ Quick Start

1. **Define your schemas (Pydantic)**

   ```python
   # server/schemas/users.py
   from microapi import Scheme

   class User(Scheme):
       username: str
       firstname: str
       lastname: str
       age: int

   class GetUserPayload(Scheme):
       user_id: int
   ```

2. **Create a service**

   ```python
   # server/services/users.py
   from microapi import Service, types
   from schemas.users import GetUserPayload, User
   from models import UserModel

   service = Service('users')

   @service.method
   async def get_user(payload: GetUserPayload) -> User:
       user = await UserModel.get(payload.user_id)
       return User.model_validate(user)
   ```

3. **Start the server**

   ```python
   # server/main.py
   from microapi import MicroAPI
   from microapi.transport import gRPC
   from services.users import service as users_service

   app = MicroAPI()
   app.add_service(users_service)

   if __name__ == '__main__':
       app.run(
           transport=gRPC(host='0.0.0.0', port=8000),
           auto_generate_lib=True,
           generated_lib_dir='shared/lib',
           refresh=True
       )
   ```

4. **Use the client**

   ```python
   # client/main.py
   from lib import users

   async def main():
       user = await users.get_user(user_id=1)
       print(user)
   ```

---

## 📂 Project Structure

```
project-root/
├── server/               # Server microservice
│   ├── services/         # Service methods (routes)
│   │   └── users.py
│   ├── schemas/          # Pydantic schemas
│   │   └── users.py
│   ├── middlewares.py    # Custom middlewares
│   └── main.py           # Entry point

├── client/               # Example client usage
│   └── main.py

└── shared/               # Auto-generated client library
    └── lib/
        └── v1/
            ├── types.py
            └── users.py
```

---

## 🛣️ Roadmap (0 → 1.0.0)

| Version | Milestones                                                                                                                 | Status         |
| ------- |----------------------------------------------------------------------------------------------------------------------------| -------------- |
| 0.1.0   | gRPC transport, Pydantic schemas, client code generation, Middleware, Dependencies, CLI, Hot Reload, Versioning            | 🔧 In Progress |
| 0.2.0   | Queue support (Kafka, RabbitMQ)                                                                                            | 🚧 Planned     |
| 0.3.0   | Integration plugins, WebSocket support, service discovery                                                                  | 🚧 Planned     |
| 0.4.0   | Auto-testing, extended docs, improved DX                                                                                   | 🚧 Planned     |
| 0.5.0   | Performance optimizations, benchmarks                                                                                      | 🚧 Planned     |
| 1.0.0   | Stable release, production-ready, complete documentation                                                                   | 🏁 Scheduled   |

---

## 🤝 Contributing

We welcome external contributions and pull requests. Check out the [issues](https://github.com/your-org/microapi/issues) for current tasks.

---

## 🙏 Acknowledgements

MicroAPI is built with inspiration and power from [Pydantic](https://docs.pydantic.dev/) and [h2](https://github.com/python-hyper/h2). Huge thanks to the authors of these amazing tools for their contribution to the Python ecosystem.

---

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

from pydantic import BaseModel


class ServerScheme(BaseModel):
    model_config = {'from_attributes': True}

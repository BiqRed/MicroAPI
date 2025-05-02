from pydantic import BaseModel


class Scheme(BaseModel):
    model_config = {'from_attributes': True}

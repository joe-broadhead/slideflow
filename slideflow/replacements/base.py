from typing import Annotated
from pydantic import BaseModel, Field

class BaseReplacement(BaseModel):
    """
    Base class for all content replacements in a slide.

    This class uses Pydantic's discriminated union feature by setting a
    `type` field as the discriminator, allowing subclasses to be selected
    based on their `type` value during deserialization.

    Attributes:
        type (str): The type identifier used for discriminated union.
    """
    type: Annotated[str, Field(description = 'The type of the replacement')]

    model_config = {
        'discriminator': 'type'
    }

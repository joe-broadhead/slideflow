import uuid
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr

class Role(str, Enum):
    """
    Valid Google Drive permission roles.

    These roles define the level of access a user has to a file or folder on Google Drive.
    """
    owner = 'owner'
    organizer = 'organizer'
    fileOrganizer = 'fileOrganizer'
    writer = 'writer'
    commenter = 'commenter'
    reader = 'reader'

class User(BaseModel):
    """
    Represents a user with an ID, email, and Google Drive permission role.

    Attributes:
        id (UUID): A unique identifier for the user.
        email (EmailStr): The user's email address.
        role (Role): The user's access level for a Google Drive file or folder.
    """
    id: UUID = Field(
        default_factory = uuid.uuid4,
        description = 'Unique identifier for the user'
    )
    email: EmailStr = Field(
        ...,
        description = 'Users email address'
    )
    role: Role = Field(
        ...,
        description = 'Google Drive permission role'
    )

    model_config = {
        'json_encoders': {
            UUID: lambda value: str(value)
        }
    }

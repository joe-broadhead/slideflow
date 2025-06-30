from pydantic import Field
from typing import Union, Annotated

from slideflow.replacements.base import BaseReplacement
from slideflow.replacements.text import TextReplacement
from slideflow.replacements.table import TableReplacement
from slideflow.replacements.ai_text import AITextReplacement
from slideflow.replacements.utils import dataframe_to_replacement_object

# Discriminated union for all replacement types
ReplacementUnion = Annotated[
    Union[TextReplacement, AITextReplacement, TableReplacement],
    Field(discriminator="type")
]

__all__ = [
    'BaseReplacement',
    'TextReplacement',
    'TableReplacement', 
    'AITextReplacement',
    'ReplacementUnion',
    'dataframe_to_replacement_object',
]

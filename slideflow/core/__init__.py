"""
Core utilities and patterns for the slideflow package.

This module contains common abstractions, registry patterns, and base classes
that are used throughout the slideflow ecosystem.
"""

from slideflow.core.registry import BaseRegistry, FunctionRegistry, ClassRegistry

__all__ = [
    "BaseRegistry",
    "FunctionRegistry", 
    "ClassRegistry",
]
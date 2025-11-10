from __future__ import annotations

import inspect
import os
from functools import cached_property
from types import UnionType
from typing import (
    Annotated,
    Any,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from asyncz import __version__  # noqa


def safe_get_type_hints(cls: type) -> dict[str, Any]:
    """
    Safely get type hints for a class, handling potential errors.
    This function attempts to retrieve type hints for the given class,
    and if it fails, it prints a warning and returns the class annotations.
    Args:
        cls (type): The class to get type hints for.
    Returns:
        dict[str, Any]: A dictionary of type hints for the class.
    """
    try:
        return get_type_hints(cls, include_extras=True)
    except Exception:
        return cls.__annotations__


class BaseSettings:
    """
    Base of all the settings for any system.
    """

    __type_hints__: dict[str, Any] = None  # type: ignore
    __truthy__: set[str] = {"true", "1", "yes", "on", "y"}

    def __init__(self, **kwargs: Any) -> None:
        """
        Initializes the settings by loading environment variables
        and casting them to the appropriate types.
        This method uses type hints from the class attributes to determine
        the expected types of the settings.
        It will look for environment variables with the same name as the class attributes,
        converted to uppercase, and cast them to the specified types.
        If an environment variable is not set, it will use the default value
        defined in the class attributes.
        """

        if kwargs:
            for key, value in kwargs.items():
                setattr(self, key, value)

        for key, typ in self.__type_hints__.items():
            base_type = self._extract_base_type(typ)

            env_value = os.getenv(key.upper(), None)
            if env_value is not None:
                value = self._cast(env_value, base_type)
            else:
                value = getattr(self, key, None)
            setattr(self, key, value)

        # Call post_init if it exists
        self.post_init()

    def __init_subclass__(cls) -> None:
        # the direct class dict has not the key
        if cls.__dict__.get("__type_hints__") is None:
            cls.__type_hints__ = safe_get_type_hints(cls)

    def post_init(self) -> None:
        """
        Post-initialization method that can be overridden by subclasses.
        This method is called after all settings have been initialized.
        """
        ...

    def _extract_base_type(self, typ: Any) -> Any:
        origin = get_origin(typ)
        if origin is Annotated:
            return get_args(typ)[0]
        return typ

    def _cast(self, value: str, typ: type[Any]) -> Any:
        """
        Casts the value to the specified type.
        If the type is `bool`, it checks for common truthy values.
        Raises a ValueError if the value cannot be cast to the type.

        Args:
            value (str): The value to cast.
            typ (type): The type to cast the value to.
        Returns:
            Any: The casted value.
        Raises:
            ValueError: If the value cannot be cast to the specified type.
        """
        try:
            origin = get_origin(typ)
            if origin is Union or origin is UnionType:
                non_none_types = [t for t in get_args(typ) if t is not type(None)]
                if len(non_none_types) == 1:
                    typ = non_none_types[0]
                else:
                    raise ValueError(f"Cannot cast to ambiguous Union type: {typ}")

            if typ is bool or str(typ) == "bool":
                return value.lower() in self.__truthy__
            return typ(value)
        except Exception:
            if get_origin(typ) is Union or get_origin(UnionType):
                type_name = " | ".join(
                    t.__name__ if hasattr(t, "__name__") else str(t) for t in get_args(typ)
                )
            else:
                type_name = getattr(typ, "__name__", str(typ))
            raise ValueError(f"Cannot cast value '{value}' to type '{type_name}'") from None

    def dict(
        self,
        exclude_none: bool = False,
        upper: bool = False,
        exclude: set[str] | None = None,
        include_properties: bool = False,
    ) -> dict[str, Any]:
        """
        Dumps all the settings into a python dictionary.
        """
        result = {}
        exclude = exclude or set()

        for key in self.__type_hints__:
            if key in exclude:
                continue
            value = getattr(self, key, None)
            if exclude_none and value is None:
                continue
            result_key = key.upper() if upper else key
            result[result_key] = value

        if include_properties:
            for name, _ in inspect.getmembers(
                type(self),
                lambda o: isinstance(
                    o,
                    (property, cached_property),
                ),
            ):
                if name in exclude or name in self.__type_hints__:
                    continue
                try:
                    value = getattr(self, name)
                    if exclude_none and value is None:
                        continue
                    result_key = name.upper() if upper else name
                    result[result_key] = value
                except Exception:
                    # Skip properties that raise errors
                    continue

        return result

    def tuple(
        self,
        exclude_none: bool = False,
        upper: bool = False,
        exclude: set[str] | None = None,
        include_properties: bool = False,
    ) -> list[tuple[str, Any]]:
        """
        Dumps all the settings into a tuple.
        """
        return list(
            self.dict(
                exclude_none=exclude_none,
                upper=upper,
                exclude=exclude,
                include_properties=include_properties,
            ).items()
        )


class Settings(BaseSettings):
    """
    Defines a comprehensive set of configuration parameters for the AsyncMQ library.

    This dataclass encapsulates various settings controlling core aspects of
    AsyncMQ's behavior, including debugging modes, logging configuration,
    default backend implementation, database connection details for different
    backends (Postgres, MongoDB), parameters for stalled job recovery,
    sandbox execution settings, worker concurrency limits, and rate limiting
    configurations. It provides a centralized place to manage and access
    these operational monkay.settings.
    """

    debug: bool = False
    """
    Enables debug mode if True.

    Debug mode may activate additional logging, detailed error reporting,
    and potentially other debugging features within the AsyncMQ system.
    Defaults to False.
    """

    version: str = __version__
    """
    Stores the current version string of the AsyncMQ library.

    This attribute holds the version information as defined in the library's
    package metadata. It's read-only and primarily for informational purposes.
    """
    secret_key: str | None = None
    """
    The secret used for cryptography and for the Dashboard to use sessions.
    """

    @property
    def dashboard_config(self) -> Any:
        """
        Retrieves the default configuration settings for the Asyncz management dashboard.

        This property dynamically imports and returns an instance of the `DashboardConfig`
        class, providing access to settings like the authentication backend, template
        directory, and static files location.

        Returns:
            An instance of `DashboardConfig`.
        """
        from asyncz.contrib.dashboard.config import DashboardConfig

        return DashboardConfig(secret_key=self.secret_key)

from fastapi import HTTPException, status


class NotFound(HTTPException):
    def __init__(self, entity: str, ident: int | str) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, f"{entity} {ident} not found")


class Forbidden(HTTPException):
    def __init__(self, detail: str = "You do not have permission to do this") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class BadRequest(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)


class Unauthorized(HTTPException):
    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)

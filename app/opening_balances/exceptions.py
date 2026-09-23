class OpeningBalanceError(Exception):
    pass


class OpeningBalanceNotFoundError(OpeningBalanceError):
    pass


class OpeningBalanceValidationError(OpeningBalanceError):
    pass


class OpeningBalancePermissionError(OpeningBalanceError):
    pass

class StockIssueError(Exception):
    pass


class StockIssueNotFoundError(StockIssueError):
    pass


class StockIssueValidationError(StockIssueError):
    pass


class StockIssuePermissionError(StockIssueError):
    pass
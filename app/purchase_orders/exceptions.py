class PurchaseOrderError(Exception):
    pass


class PurchaseOrderNotFoundError(PurchaseOrderError):
    pass


class PurchaseOrderPermissionError(PurchaseOrderError):
    pass


class PurchaseOrderValidationError(PurchaseOrderError):
    pass
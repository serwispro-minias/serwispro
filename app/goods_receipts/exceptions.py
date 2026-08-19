class GoodsReceiptError(Exception):
    pass


class GoodsReceiptNotFoundError(GoodsReceiptError):
    pass


class GoodsReceiptValidationError(GoodsReceiptError):
    pass


class GoodsReceiptPermissionError(GoodsReceiptError):
    pass
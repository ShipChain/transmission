class WalletInUseException(Exception):
    """The Wallet is currently in use by another AsyncJob"""
    pass


class TransactionCollisionException(Exception):
    """The Wallet is currently in use by another AsyncJob"""
    pass

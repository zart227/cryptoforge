from freqtrade.exceptions import OperationalException

from CryptoForgeSmallBalancePilotStrategy import CryptoForgeSmallBalancePilotStrategy


class CryptoForgeActivePaperStrategy(CryptoForgeSmallBalancePilotStrategy):
    """Dynamic-universe experiment with the pilot's unchanged risk limits."""

    def bot_start(self, **kwargs):
        if self.config.get("dry_run") is not True:
            raise OperationalException("Active universe strategy requires dry_run=true")

    def entry_pair_allowed(self, pair: str) -> bool:
        return (
            self.config.get("dry_run") is True
            and self.dp is not None
            and pair in self.dp.current_whitelist()
        )

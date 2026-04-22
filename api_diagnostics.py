#!/usr/bin/env python3
"""
Bybit API Diagnostics Tool

Automatically checks API key validity for testnet and mainnet environments.
"""
import os
import sys
import time
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class APIDiagnosticResult:
    """Result of API diagnostic check"""
    testnet_status: str  # "ok", "invalid", "permission", "error"
    mainnet_status: str  # "ok", "invalid", "permission", "error"
    recommended: str     # "testnet", "mainnet", "none"
    testnet_error: Optional[str] = None
    mainnet_error: Optional[str] = None
    account_type: Optional[str] = None
    balances: Optional[Dict] = None


class APIDiagnostics:
    """Bybit API diagnostics checker"""
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet_url = "https://api-testnet.bybit.com"
        self.mainnet_url = "https://api.bybit.com"
        self.max_retries = 3
        self.retry_delay = 1.0
        
    def _check_endpoint(self, use_testnet: bool) -> Tuple[str, Optional[str], Optional[Dict]]:
        """
        Check API endpoint with retry logic.
        
        Returns:
            (status, error_message, account_info)
            status: "ok", "invalid", "permission", "error"
        """
        url = self.testnet_url if use_testnet else self.mainnet_url
        env_name = "TESTNET" if use_testnet else "MAINNET"
        
        for attempt in range(self.max_retries):
            try:
                import requests
                import hmac
                import hashlib
                import json
                
                timestamp = str(int(time.time() * 1000))
                recv_window = "5000"
                
                # Test wallet balance endpoint
                query = "accountType=UNIFIED"
                param = timestamp + self.api_key + recv_window + query
                signature = hmac.new(
                    self.api_secret.encode('utf-8'),
                    param.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                headers = {
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": recv_window,
                    "Content-Type": "application/json"
                }
                
                endpoint_url = f"{url}/v5/account/wallet-balance?{query}"
                logger.info(f"[{env_name}] Attempt {attempt + 1}/{self.max_retries}: Checking wallet balance...")
                
                response = requests.get(endpoint_url, headers=headers, timeout=10)
                data = response.json()
                
                ret_code = data.get("retCode", -1)
                ret_msg = data.get("retMsg", "")
                
                # Handle specific error codes
                if ret_code == 10003:
                    return "invalid", f"Invalid API key: {ret_msg}", None
                elif ret_code == 10005:
                    return "permission", f"Permission denied: {ret_msg}", None
                elif ret_code == 10006:
                    return "permission", f"IP restriction: {ret_msg}", None
                elif ret_code == 10016:
                    return "permission", f"API key expired: {ret_msg}", None
                elif ret_code != 0:
                    return "error", f"API error {ret_code}: {ret_msg}", None
                
                # Success - extract account info
                result = data.get("result", {})
                account_list = result.get("list", [])
                
                if not account_list:
                    return "ok", None, {"account_type": "unknown", "balances": {}}
                
                account_info = account_list[0]
                account_type = account_info.get("accountType", "UNIFIED")
                
                # Extract balances
                balances = {}
                for coin in account_info.get("coin", []):
                    coin_name = coin.get("coin", "")
                    wallet_balance = coin.get("walletBalance", "0")
                    if float(wallet_balance) > 0:
                        balances[coin_name] = wallet_balance
                
                logger.info(f"[{env_name}] ✅ OK - Account type: {account_type}, Balances: {len(balances)} coins")
                
                return "ok", None, {
                    "account_type": account_type,
                    "balances": balances
                }
                
            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    logger.warning(f"[{env_name}] Timeout, retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    return "error", "Request timeout", None
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"[{env_name}] Connection error, retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    return "error", f"Connection error: {str(e)}", None
                    
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"[{env_name}] Error: {e}, retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    return "error", f"Unexpected error: {str(e)}", None
        
        return "error", "Max retries exceeded", None
    
    def diagnose(self) -> APIDiagnosticResult:
        """
        Diagnose API key for both testnet and mainnet.
        
        Returns:
            APIDiagnosticResult with status and recommendations
        """
        logger.info("=" * 60)
        logger.info("BYBIT API DIAGNOSTICS")
        logger.info("=" * 60)
        logger.info(f"API Key: {self.api_key[:10]}...{self.api_key[-4:]}")
        logger.info(f"API Secret: {self.api_secret[:10]}...{self.api_secret[-4:]}")
        logger.info("-" * 60)
        
        # Check testnet first
        testnet_status, testnet_error, testnet_info = self._check_endpoint(use_testnet=True)
        
        # Check mainnet
        mainnet_status, mainnet_error, mainnet_info = self._check_endpoint(use_testnet=False)
        
        # Determine recommendation
        recommended = "none"
        account_type = None
        balances = None
        
        if testnet_status == "ok":
            recommended = "testnet"
            account_type = testnet_info.get("account_type") if testnet_info else None
            balances = testnet_info.get("balances") if testnet_info else None
        elif mainnet_status == "ok":
            recommended = "mainnet"
            account_type = mainnet_info.get("account_type") if mainnet_info else None
            balances = mainnet_info.get("balances") if mainnet_info else None
        elif testnet_status == "permission" and mainnet_status == "permission":
            recommended = "none"  # Permission issues on both
        elif testnet_status == "invalid" and mainnet_status == "invalid":
            recommended = "none"  # Invalid key on both
        elif testnet_status == "error" and mainnet_status == "ok":
            recommended = "mainnet"
        elif mainnet_status == "error" and testnet_status == "ok":
            recommended = "testnet"
        
        # Print results
        logger.info("-" * 60)
        logger.info(f"[TESTNET] {'✅ OK' if testnet_status == 'ok' else '❌ ' + testnet_status.upper()}")
        if testnet_error:
            logger.info(f"  Error: {testnet_error}")
        
        logger.info(f"[MAINNET] {'✅ OK' if mainnet_status == 'ok' else '❌ ' + mainnet_status.upper()}")
        if mainnet_error:
            logger.info(f"  Error: {mainnet_error}")
        
        logger.info("-" * 60)
        
        if recommended == "testnet":
            logger.info(f"→ RESULT: Use testnet (testnet=True)")
        elif recommended == "mainnet":
            logger.info(f"→ RESULT: Use mainnet (testnet=False)")
        else:
            logger.info(f"→ RESULT: API key invalid or has permission issues")
        
        if account_type and balances:
            logger.info(f"Account type: {account_type}")
            logger.info(f"Balances: {balances}")
        
        logger.info("=" * 60)
        
        return APIDiagnosticResult(
            testnet_status=testnet_status,
            mainnet_status=mainnet_status,
            recommended=recommended,
            testnet_error=testnet_error,
            mainnet_error=mainnet_error,
            account_type=account_type,
            balances=balances
        )


def diagnose_api(api_key: str, api_secret: str) -> dict:
    """
    Diagnose API key validity.
    
    Args:
        api_key: Bybit API key
        api_secret: Bybit API secret
    
    Returns:
        dict with diagnostic results:
        {
            "testnet": "ok / invalid / permission / error",
            "mainnet": "ok / invalid / permission / error",
            "recommended": "testnet / mainnet / none",
            "testnet_error": str or None,
            "mainnet_error": str or None,
            "account_type": str or None,
            "balances": dict or None
        }
    """
    diagnostics = APIDiagnostics(api_key, api_secret)
    result = diagnostics.diagnose()
    
    return {
        "testnet": result.testnet_status,
        "mainnet": result.mainnet_status,
        "recommended": result.recommended,
        "testnet_error": result.testnet_error,
        "mainnet_error": result.mainnet_error,
        "account_type": result.account_type,
        "balances": result.balances
    }


def main():
    """CLI entry point"""
    # Get API credentials from environment or command line
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    
    # Support command line arguments
    if len(sys.argv) >= 3:
        api_key = sys.argv[1]
        api_secret = sys.argv[2]
    
    if not api_key or not api_secret:
        logger.error("❌ BYBIT_API_KEY and BYBIT_API_SECRET must be set")
        logger.info("Usage:")
        logger.info("  python api_diagnostics.py <api_key> <api_secret>")
        logger.info("  OR")
        logger.info("  export BYBIT_API_KEY='your_key'")
        logger.info("  export BYBIT_API_SECRET='your_secret'")
        logger.info("  python api_diagnostics.py")
        sys.exit(1)
    
    # Run diagnostics
    result = diagnose_api(api_key, api_secret)
    
    # Exit with appropriate code
    if result["recommended"] in ["testnet", "mainnet"]:
        logger.info("✅ API key is valid")
        sys.exit(0)
    else:
        logger.error("❌ API key is invalid or has permission issues")
        sys.exit(1)


if __name__ == "__main__":
    main()

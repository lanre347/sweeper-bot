import time
import json
from web3 import Web3
from eth_account import Account

# === CONFIG ===
INFURA_URL = "https://eth-mainnet.g.alchemy.com/v2/cRFWsRHRt7Pw8tdynGj0zViQVQi2fhkP"
CHAIN_ID = 1
GAS_WAIT_INTERVAL = 2  # seconds between gas price re-checks
CHECK_INTERVAL = 10    # seconds BETWEEN FULL CYCLES
GAS_LIMIT = 700000

# === ERC20 ABI ===
ERC20_ABI = json.loads("""
[
    {
        "constant": true,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]
""")

# === CONNECT TO WEB3 ===
web3 = Web3(Web3.HTTPProvider(INFURA_URL))
assert web3.is_connected(), "Failed to connect to RPC"

# === FILE LOADERS ===
def load_private_keys(filename="private_keys.txt"):
    with open(filename, "r") as f:
        return [line.strip() for line in f if line.strip()]

def load_receiver(filename="wallets.txt"):
    with open(filename, "r") as f:
        return f.readline().strip()

def load_token_addresses(filename="tokens.txt"):
    with open(filename, "r") as f:
        return [line.strip() for line in f if line.strip()]

# === GAS PRICE CHECKER ===
def wait_for_transaction_fee_limit(gas_limit, max_fee_eth):
    while True:
        gas_price = web3.eth.gas_price
        estimated_fee = Web3.from_wei(gas_price * gas_limit, 'ether')
        if estimated_fee <= max_fee_eth:
            return gas_price
        print(f"Gas fee too high ({estimated_fee:.8f} ETH), waiting...")
        time.sleep(GAS_WAIT_INTERVAL)

# === BALANCE CHECKERS ===
def get_token_balance(token_address, wallet_address):
    try:
        token = web3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
        return token.functions.balanceOf(wallet_address).call()
    except Exception as e:
        print(f"Error fetching balance for {wallet_address} on token {token_address}: {e}")
        return 0

def get_eth_balance(wallet_address):
    try:
        return web3.eth.get_balance(wallet_address)
    except Exception as e:
        print(f"Error fetching ETH balance for {wallet_address}: {e}")
        return 0

# === SEND FUNCTIONS ===
def send_token(private_key, token_address, to_address, amount, gas_price):
    account = Account.from_key(private_key)
    sender = account.address

    token = web3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
    nonce = web3.eth.get_transaction_count(sender)

    txn = token.functions.transfer(
        Web3.to_checksum_address(to_address),
        amount
    ).build_transaction({
        'chainId': CHAIN_ID,
        'gas': GAS_LIMIT,
        'gasPrice': gas_price,
        'nonce': nonce
    })

    signed = web3.eth.account.sign_transaction(txn, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Sent {amount} of {token_address} from {sender} to {to_address} | TX: {tx_hash.hex()}")
    return tx_hash

def send_eth(private_key, to_address, amount_wei, gas_price):
    account = Account.from_key(private_key)
    sender = account.address
    nonce = web3.eth.get_transaction_count(sender)

    txn = {
        'chainId': CHAIN_ID,
        'to': Web3.to_checksum_address(to_address),
        'value': amount_wei,
        'gas': 21000,
        'gasPrice': gas_price,
        'nonce': nonce
    }

    signed = web3.eth.account.sign_transaction(txn, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Sent {Web3.from_wei(amount_wei, 'ether')} ETH from {sender} to {to_address} | TX: {tx_hash.hex()}")
    return tx_hash

# === SWEEPERS ===
def sweep_tokens(max_fee_eth):
    private_keys = load_private_keys()
    token_addresses = load_token_addresses()
    receiver_address = load_receiver()

    while True:
        print("\nStarting token sweep cycle...")
        for token_address in token_addresses:
            print(f"\nProcessing token: {token_address}")
            for pk in private_keys:
                account = Account.from_key(pk)
                sender = account.address
                balance = get_token_balance(token_address, sender)

                if balance > 0:
                    print(f"{sender} has {balance} of token {token_address}")
                    try:
                        gas_price = wait_for_transaction_fee_limit(GAS_LIMIT, max_fee_eth)
                        send_token(pk, token_address, receiver_address, balance, gas_price)
                    except Exception as e:
                        print(f"Failed to send from {sender} for token {token_address}: {e}")
                else:
                    print(f"{sender} has no balance of token {token_address}")

        print(f"\nFinished token scan. Waiting {CHECK_INTERVAL} seconds...\n")
        time.sleep(CHECK_INTERVAL)

def sweep_eth(max_fee_eth):
    private_keys = load_private_keys()
    receiver_address = load_receiver()

    while True:
        print("\nStarting ETH sweep cycle...")
        for pk in private_keys:
            account = Account.from_key(pk)
            sender = account.address
            balance_wei = get_eth_balance(sender)

            if balance_wei > 21000 * web3.eth.gas_price:
                send_amount = balance_wei - (21000 * web3.eth.gas_price)
                if send_amount > 0:
                    print(f"{sender} has {Web3.from_wei(balance_wei, 'ether')} ETH")
                    try:
                        gas_price = wait_for_transaction_fee_limit(21000, max_fee_eth)
                        send_eth(pk, receiver_address, send_amount, gas_price)
                    except Exception as e:
                        print(f"Failed to send ETH from {sender}: {e}")
                else:
                    print(f"{sender} has ETH but not enough after gas fee deduction")
            else:
                print(f"{sender} has insufficient ETH to send")

        print(f"\nFinished ETH scan. Waiting {CHECK_INTERVAL} seconds...\n")
        time.sleep(CHECK_INTERVAL)

def sweep_eth_and_tokens(max_fee_eth):
    private_keys = load_private_keys()
    token_addresses = load_token_addresses()
    receiver_address = load_receiver()

    while True:
        print("\nStarting UNIVERSAL sweep cycle...")
        for pk in private_keys:
            account = Account.from_key(pk)
            sender = account.address

            # Sweep ETH first
            balance_wei = get_eth_balance(sender)
            if balance_wei > 21000 * web3.eth.gas_price:
                send_amount = balance_wei - (21000 * web3.eth.gas_price)
                if send_amount > 0:
                    print(f"{sender} has {Web3.from_wei(balance_wei, 'ether')} ETH")
                    try:
                        gas_price = wait_for_transaction_fee_limit(21000, max_fee_eth)
                        send_eth(pk, receiver_address, send_amount, gas_price)
                    except Exception as e:
                        print(f"Failed to send ETH from {sender}: {e}")
                else:
                    print(f"{sender} has ETH but not enough after gas fee deduction")
            else:
                print(f"{sender} has insufficient ETH to send")

            # Sweep tokens next
            for token_address in token_addresses:
                balance = get_token_balance(token_address, sender)
                if balance > 0:
                    print(f"{sender} has {balance} of token {token_address}")
                    try:
                        gas_price = wait_for_transaction_fee_limit(GAS_LIMIT, max_fee_eth)
                        send_token(pk, token_address, receiver_address, balance, gas_price)
                    except Exception as e:
                        print(f"Failed to send token {token_address} from {sender}: {e}")
                else:
                    print(f"{sender} has no balance of token {token_address}")

        print(f"\nFinished UNIVERSAL scan. Waiting {CHECK_INTERVAL} seconds...\n")
        time.sleep(CHECK_INTERVAL)

# === ENTRY POINT ===
if __name__ == "__main__":
    print("\n--- SWEEP MODE ---")
    print("1. Sweep ETH only")
    print("2. Sweep tokens only")
    print("3. Sweep BOTH ETH and tokens (universal)")
    choice = input("Enter choice (1/2/3): ").strip()

    max_fee_eth = float(input("Enter max gas fee in ETH (e.g. 0.0001): "))

    if choice == "1":
        sweep_eth(max_fee_eth)
    elif choice == "2":
        sweep_tokens(max_fee_eth)
    elif choice == "3":
        sweep_eth_and_tokens(max_fee_eth)
    else:
        print("Invalid choice.")

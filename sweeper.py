# -*- coding: utf-8 -*-
from web3 import Web3
import time
import requests

# Connect to the Arbitrum Mainnet via Infura
infura_url = "https://arbitrum-mainnet.infura.io/v3/811adce7b53e4365b8422ea624685d9f"
web3 = Web3(Web3.HTTPProvider(infura_url, request_kwargs={'timeout': 60}))

# Check connection
if not web3.is_connected():
    raise Exception("Failed to connect to Arbitrum network")

# Constants
CHAIN_ID = 42161
MAX_RETRIES = 5
RETRY_DELAY = 3
GAS_WAIT_INTERVAL = 2  # Seconds between gas price checks
CHECK_INTERVAL = 0.01  # 10 milliseconds
PRIVATE_KEY = "YOUR_PRIVATE_KEY_HERE"  # Replace with your key securely

# Load recipient wallet addresses
def load_wallet_addresses(filename="wallets.txt"):
    with open(filename, "r") as file:
        return [line.strip() for line in file.readlines() if line.strip()]

# Wait for acceptable gas price
def wait_for_transaction_fee_limit(gas_limit, max_fee_eth):
    while True:
        gas_price = web3.eth.gas_price
        estimated_fee_eth = Web3.from_wei(gas_price * gas_limit, 'ether')
        if estimated_fee_eth <= max_fee_eth:
            return gas_price
        print(f"Fee too high: {estimated_fee_eth:.10f} ETH > {max_fee_eth} ETH. Retrying...")
        time.sleep(GAS_WAIT_INTERVAL)

# Calculate max amount to send (accounting for gas fee)
def calculate_max_sendable_eth(balance_wei, gas_price, gas_limit):
    fee_wei = gas_price * gas_limit
    if balance_wei > fee_wei:
        return balance_wei - fee_wei
    return 0

# Send full ETH balance
def send_max_eth(private_key, to_address, max_fee_eth):
    sender_address = web3.eth.account.from_key(private_key).address
    balance = web3.eth.get_balance(sender_address)

    try:
        estimated_gas_limit = web3.eth.estimate_gas({
            'from': sender_address,
            'to': to_address,
            'value': 1
        })
    except:
        estimated_gas_limit = 21000  # Fallback

    gas_limit = int(estimated_gas_limit * 1.2)
    gas_price = wait_for_transaction_fee_limit(gas_limit, max_fee_eth)

    sendable_wei = calculate_max_sendable_eth(balance, gas_price, gas_limit)
    if sendable_wei <= 0:
        return False  # Will retry next loop

    tx = {
        'nonce': web3.eth.get_transaction_count(sender_address),
        'to': to_address,
        'value': int(sendable_wei),
        'gas': gas_limit,
        'gasPrice': int(gas_price),
        'chainId': CHAIN_ID
    }

    signed_tx = web3.eth.account.sign_transaction(tx, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"Sent {Web3.from_wei(sendable_wei, 'ether')} ETH to {to_address}. Tx: {web3.to_hex(tx_hash)}")
    return True

# Continuous check and send loop
def monitor_and_send():
    max_fee_eth = float(input("Enter max transaction fee in ETH (e.g. 0.0001): ").strip())
    sender_address = web3.eth.account.from_key(PRIVATE_KEY).address
    wallets = load_wallet_addresses()

    print(f"Monitoring address: {sender_address}")
    print(f"Loaded {len(wallets)} recipient wallets")

    sent_to = set()

    while True:
        balance = web3.eth.get_balance(sender_address)
        if balance > 0:
            for address in wallets:
                if address not in sent_to:
                    try:
                        success = send_max_eth(PRIVATE_KEY, address, max_fee_eth)
                        if success:
                            sent_to.add(address)
                            break  # Send to one wallet per loop
                    except Exception as e:
                        print(f"Error sending to {address}: {e}")
        time.sleep(CHECK_INTERVAL)

# Main entry
if __name__ == "__main__":
    monitor_and_send()

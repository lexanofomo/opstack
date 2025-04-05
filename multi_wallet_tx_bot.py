from web3 import Web3
import concurrent.futures
import time
import os

ALL_NETWORKS = {
    "Optimism": {"rpc": "https://optimism-mainnet.public.blastapi.io", "chain_id": 10},
    "Base": {"rpc": "https://gateway.tenderly.co/public/base", "chain_id": 8453},
    "Unichain": {"rpc": "https://unichain-rpc.publicnode.com", "chain_id": 130},
    "Soneinium": {"rpc": "https://rpc.soneium.org", "chain_id": 1868},
    "Ink": {"rpc": "https://rpc-qnd.inkonchain.com", "chain_id": 57073},
    "Mode": {"rpc": "https://mainnet.mode.network", "chain_id": 34443},
    "Lisk": {"rpc": "https://rpc.api.lisk.com", "chain_id": 1135}
}

TX_TARGET = 250 # нужное количество транзакций
VALUE_WEI = Web3.to_wei(0.00001, "ether") # кол-во отправляемого eth
DELAY_BETWEEN_TX = 0.25  # задержка между транзакциями, секунд

def load_wallets(filename="wallets.txt"): #загрузка кошельков из текстового файла
    wallets = []
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Файл {filename} не найден!")
    with open(filename, "r") as f:
        for line in f:
            if ":" in line:
                addr, key = line.strip().split(":")
                wallets.append((addr.strip(), key.strip()))
    return wallets

def send_transactions(wallet_name, net_name, config, address, private_key):
    w3 = Web3(Web3.HTTPProvider(config["rpc"]))
    chain_id = config["chain_id"]

    try:
        start_nonce = w3.eth.get_transaction_count(address, 'pending')
        if start_nonce >= TX_TARGET:
            print(f"⚠️ {wallet_name}: {net_name} уже отправлено {start_nonce} tx, пропуск.")
            return 0

        target_nonce = TX_TARGET  # TX_TARGET - конечное желаемое количество транзакций в X чейне
        tx_to_send = target_nonce - start_nonce
        print(f"\n▶ {wallet_name}: {net_name} отправка {tx_to_send} tx, начиная с nonce {start_nonce}")
        tx_sent = 0
        current_nonce = start_nonce

        while current_nonce < target_nonce:
            gas_price = w3.eth.gas_price
            tx = {
                'nonce': current_nonce,
                'to': address,
                'value': VALUE_WEI,
                'gas': 21000,
                'gasPrice': gas_price,
                'chainId': chain_id
            }
            retries = 3
            while retries > 0:
                try:
                    signed_tx = w3.eth.account.sign_transaction(tx, private_key)
                    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                    print(f"{wallet_name} {net_name} TX {current_nonce+1}/{target_nonce}: {Web3.to_hex(tx_hash)}")
                    tx_sent += 1
                    current_nonce += 1  # успешно отправлено – переходим к следующему nonce
                    break  # выходим из цикла повторов для этого nonce
                except Exception as e:
                    error_str = str(e).lower()
                    if "nonce too low" in error_str:
                        new_nonce = w3.eth.get_transaction_count(address, 'pending')
                        print(f"⚠️ {wallet_name} {net_name}: nonce too low, обновление с {current_nonce} до {new_nonce}")
                        current_nonce = new_nonce
                        break
                    elif "insufficient funds" in error_str or "overshot" in error_str:
                        print(f"⚠️ {wallet_name} {net_name}: недостаточно средств для nonce {current_nonce}. Повтор через 3с...")
                        time.sleep(3)
                        retries = 3  # сброс попыток для этого nonce, количество повторений
                        continue
                    else:
                        print(f"⚠️ {wallet_name} {net_name} nonce {current_nonce}: ошибка {str(e)} — повтор через 3с...")
                        time.sleep(3)
                        retries -= 1
            if retries == 0:
                print(f"❌ {wallet_name} {net_name} nonce {current_nonce}: не удалось отправить tx после нескольких попыток.")
                current_nonce += 1

        print(f"✅ {wallet_name} {net_name}: отправлено {tx_sent} tx.\n")
        return tx_sent
    except Exception as e:
        print(f"❌ {wallet_name} {net_name} критическая ошибка: {str(e)}")
        return 0

def run_wallet(wallet_index, address, private_key, networks):
    wallet_name = f"Wallet {wallet_index}"
    tx_counts = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            net_name: executor.submit(send_transactions, wallet_name, net_name, config, address, private_key)
            for net_name, config in networks.items()
        }
        for net_name, future in futures.items():
            try:
                tx_counts[net_name] = future.result()
            except Exception as e:
                tx_counts[net_name] = 0
    return wallet_index, tx_counts

def get_balances(wallets, networks): #получаем балансы
    net_instances = {
        net_name: Web3(Web3.HTTPProvider(config["rpc"]))
        for net_name, config in networks.items()
    }
    balances = {}
    for wallet_index, (address, _) in enumerate(wallets, start=1):
        wallet_balances = {}
        address_checksum = Web3.to_checksum_address(address)
        for net_name, w3 in net_instances.items():
            try:
                balance = w3.eth.get_balance(address_checksum)
                balance_eth = w3.from_wei(balance, "ether")
            except Exception as e:
                balance_eth = 0
            wallet_balances[net_name] = balance_eth
        balances[wallet_index] = wallet_balances
    return balances

# отображение балансов
def check_balances(wallets, networks):
    print("\nБаланс кошельков:")
    net_instances = {
        net_name: Web3(Web3.HTTPProvider(config["rpc"]))
        for net_name, config in networks.items()
    }
    for wallet_index, (address, _) in enumerate(wallets, start=1):
        wallet_name = f"Wallet {wallet_index}"
        balances_info = []
        address_checksum = Web3.to_checksum_address(address)
        for net_name, w3 in net_instances.items():
            try:
                balance = w3.eth.get_balance(address_checksum)
                balance_eth = w3.from_wei(balance, "ether")
            except Exception as e:
                balance_eth = 0
            balances_info.append(f"{net_name} - {balance_eth:.6f} ETH")
        print(f"{wallet_name}: {', '.join(balances_info)}")

if __name__ == "__main__":
    wallets = load_wallets()

    print("Доступные блокчейны:", ", ".join(ALL_NETWORKS.keys()))
    selected_chains = input("Введите блокчейны через запятую (или 'all' для всех): ").strip()

    if selected_chains.lower() == 'all':
        networks = ALL_NETWORKS
    else:
        chosen = [chain.strip().capitalize() for chain in selected_chains.split(",") if chain.strip().capitalize() in ALL_NETWORKS]
        networks = {chain: ALL_NETWORKS[chain] for chain in chosen}

    # вывод балансов до отправки транзакций
    check_balances(wallets, networks)

    proceed = input("\nНачать отправку транзакций? (y/n): ")
    wallet_results = []
    if proceed.lower() == "y":
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(wallets)) as wallet_executor:
            wallet_futures = [
                wallet_executor.submit(run_wallet, idx+1, addr, pk, networks)
                for idx, (addr, pk) in enumerate(wallets)
            ]
            for future in concurrent.futures.as_completed(wallet_futures):
                wallet_results.append(future.result())
    else:
        print("Отправка транзакций отменена пользователем.")
        print("Отправка транзакций отменена пользователем.")

    # получаем актуальные балансы после отправки транзакций
    final_balances = get_balances(wallets, networks)

    # выводим итоговый отчет
    print("\nИтоговый отчет:")
    for wallet_index, tx_counts in sorted(wallet_results, key=lambda x: x[0]):
        wallet_name = f"Wallet {wallet_index}"
        wallet_balances = final_balances.get(wallet_index, {})
        report_lines = []
        for net in networks.keys():
            bal = wallet_balances.get(net, 0)
            tx_count = tx_counts.get(net, 0)
            report_lines.append(f"{net}: {bal:.6f} ETH, {tx_count} tx")
        report_str = "; ".join(report_lines)
        print(f"{wallet_name}: {report_str}")

    input("\nНажмите Enter, чтобы выйти...")

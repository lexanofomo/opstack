import logging
import os
import time
import random
import requests
import concurrent.futures
from web3 import Web3
from eth_account import Account


class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',
        'INFO': '\033[92m',
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
        'CRITICAL': '\033[95m'
    }
    RESET = '\033[0m'
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.msg = f"{color}{record.msg}{self.RESET}"
        return super().format(record)

handler = logging.StreamHandler()
formatter = ColoredFormatter('[%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger()

########################################
# 2. Загрузка прокси из файла proxies.txt
########################################
def load_proxies(filename="proxies.txt"):
    proxies = []
    if os.path.exists(filename):
        with open(filename, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) == 4:
                    host, port, username, password = parts
                    proxy_url = f"http://{username}:{password}@{host}:{port}"
                else:
                    proxy_url = line
                proxies.append(proxy_url)
    return proxies

PROXIES = load_proxies()
if PROXIES:
    logger.info(f"Прокси используются: найдено {len(PROXIES)} прокси.")
else:
    logger.info("Прокси не используются.")

########################################
# 3. Создание и кэширование с прокси
########################################
WEB3_CACHE = {}
def get_web3(rpc):
    if rpc in WEB3_CACHE:
        return WEB3_CACHE[rpc]
    else:
        if PROXIES:
            proxy = random.choice(PROXIES)
            logger.info(f"Используется прокси для Web3: {proxy}")
            provider = Web3.HTTPProvider(rpc, request_kwargs={"proxies": {"http": proxy, "https": proxy}})
        else:
            provider = Web3.HTTPProvider(rpc)
        w3_obj = Web3(provider)
        WEB3_CACHE[rpc] = w3_obj
        return w3_obj

########################################
# 4. Конфигурация блокчейнов
########################################
chain_info = {
    'optimism': {
        'rpc': 'https://optimism-mainnet.public.blastapi.io',
        'chain_id': 10
    },
    'base': {
        'rpc': 'https://mainnet.base.org',
        'chain_id': 8453
    },
    'mode': {
        'rpc': 'https://mode.drpc.org',
        'chain_id': 34443
    },
    'ink': {
        'rpc': 'https://rpc-qnd.inkonchain.com',
        'chain_id': 57073
    },
    'soneinium': {
        'rpc': 'https://rpc.soneium.org',
        'chain_id': 1868
    },
    'unichain': {
        'rpc': 'https://unichain-rpc.publicnode.com',
        'chain_id': 130
    },
    'lisk': {
        'rpc': 'https://rpc.lisk.io',
        'chain_id': 1135
    }
}

########################################
# 5. Параметры операций
########################################
# Для рассылки (Disperse)
SEND_AMOUNT_ETH = 0.0005   # Сумма, отправляемая каждому получателю
THRESHOLD_ETH = 0.00001   # Если баланс получателя выше – рассылка не производится
GAS_LIMIT = 21000
DELAY_BETWEEN_TX = 0.15

# Для сбора (Collect)
FIXED_GAS_PRICE = 1000000000  # 1 Gwei
COLLECT_PERCENTAGE = 0.95     # Собрать 95% средств (после вычета газа)

########################################
# 6. Загрузка кошельков (wallets.txt)
########################################
def load_wallets(filename="wallets.txt"):
    if not os.path.exists(filename):
        logger.error("Файл wallets.txt не найден!")
        exit(1)
    wallets = []
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if ":" in line:
                addr, key = line.split(":", 1)
                wallets.append((addr.strip(), key.strip()))
    return wallets

########################################
# 7. Функция рассылки для одной сети (Disperse)
########################################
def disperse_for_network(sender, recipients, config):
    w3 = get_web3(config["rpc"])
    chain_id = config["chain_id"]
    sender_address, sender_key = sender
    sender_address = Web3.to_checksum_address(sender_address)
    sender_nonce = w3.eth.get_transaction_count(sender_address, 'pending')
    logger.info(f"[Disperse][{chain_id}]: Отправитель {sender_address} – nonce: {sender_nonce}")
    success_count = 0

    for idx, recipient in enumerate(recipients, start=1):
        rec_address, _ = recipient
        rec_address = Web3.to_checksum_address(rec_address)
        balance = w3.eth.get_balance(rec_address)
        balance_eth = float(w3.from_wei(balance, "ether"))
        if balance_eth > THRESHOLD_ETH:
            logger.info(f"[Disperse][{chain_id}]: Получатель {rec_address} имеет баланс {balance_eth:.6f} ETH, пропуск.")
            continue

        tx = {
            'nonce': sender_nonce,
            'to': rec_address,
            'value': Web3.to_wei(SEND_AMOUNT_ETH, "ether"),
            'gas': GAS_LIMIT,
            'gasPrice': w3.eth.gas_price,
            'chainId': chain_id
        }
        retries = 3
        while retries > 0:
            try:
                signed_tx = w3.eth.account.sign_transaction(tx, sender_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                logger.info(f"[Disperse][{chain_id}]: TX {Web3.to_hex(tx_hash)} отправлена на {rec_address} ({idx}/{len(recipients)})")
                success_count += 1
                sender_nonce += 1
                break
            except Exception as e:
                logger.warning(f"[Disperse][{chain_id}]: Ошибка отправки с {sender_address} на {rec_address}: {str(e)}. Повтор через 3 сек...")
                time.sleep(3)
                retries -= 1
        if retries == 0:
            logger.error(f"[Disperse][{chain_id}]: Не удалось отправить TX на {rec_address} после нескольких попыток.")
        time.sleep(DELAY_BETWEEN_TX)
    final_nonce = w3.eth.get_transaction_count(sender_address, 'pending')
    logger.info(f"[Disperse][{chain_id}]: Завершено: отправлено {success_count} TX (nonce: {final_nonce}).")
    return success_count

########################################
# 8. Функция рассылки по выбранным сетям (Disperse All)
########################################
def disperse_all_networks(sender, recipients, selected_networks):
    overall_results = {}
    for net in selected_networks:
        config = chain_info[net]
        logger.info(f"\n[Disperse] Сеть: {net}")
        count = disperse_for_network(sender, recipients, config)
        overall_results[net] = count
    return overall_results

########################################
# 9. Функция сбора для одной сети (Collect)
########################################
def collect_for_network(main_wallet, donor_wallets, config, gas_limit=GAS_LIMIT, fixed_gas_price=FIXED_GAS_PRICE, percentage=COLLECT_PERCENTAGE):
    w3 = get_web3(config["rpc"])
    chain_id = config["chain_id"]
    main_address = Web3.to_checksum_address(main_wallet[0])
    collected_txs = []
    for donor in donor_wallets:
        donor_address, donor_key = donor
        donor_address = Web3.to_checksum_address(donor_address)
        balance = w3.eth.get_balance(donor_address)
        gas_cost = gas_limit * fixed_gas_price
        if balance <= gas_cost:
            logger.info(f"[Collect][{chain_id}]: Кошелек {donor_address} не может оплатить газ (баланс: {balance}).")
            continue
        amount_to_send = int(percentage * (balance - gas_cost))
        if amount_to_send <= 0:
            logger.info(f"[Collect][{chain_id}]: Кошелек {donor_address} не имеет средств для перевода после вычета газа.")
            continue
        nonce = w3.eth.get_transaction_count(donor_address, 'pending')
        current_gas_price = fixed_gas_price
        tx = {
            'nonce': nonce,
            'to': main_address,
            'value': amount_to_send,
            'gas': gas_limit,
            'gasPrice': current_gas_price,
            'chainId': chain_id
        }
        retries = 3
        sent = False
        while retries > 0:
            try:
                tx['nonce'] = nonce
                tx['gasPrice'] = current_gas_price
                signed_tx = w3.eth.account.sign_transaction(tx, donor_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                logger.info(f"[Collect][{chain_id}]: TX {Web3.to_hex(tx_hash)} отправлена с {donor_address} на {main_address}. Ожидание подтверждения (10 сек)...")
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=10)
                if receipt and receipt.status == 1:
                    logger.info(f"[Collect][{chain_id}]: TX {Web3.to_hex(tx_hash)} подтверждена.")
                    collected_txs.append(tx_hash)
                    sent = True
                    break
                else:
                    raise Exception("TX не подтверждена")
            except Exception as e:
                logger.warning(f"[Collect][{chain_id}]: Ошибка отправки TX с {donor_address} (nonce {nonce}): {str(e)}. Повтор через 3 сек...")
                time.sleep(3)
                retries -= 1
                if retries > 0:
                    if "nonce too low" in str(e).lower():
                        new_nonce = w3.eth.get_transaction_count(donor_address, 'pending')
                        logger.warning(f"[Collect][{chain_id}]: Обновление nonce с {nonce} до {new_nonce} для {donor_address}.")
                        nonce = new_nonce
                    else:
                        current_gas_price = int(current_gas_price * 1.2)
                        logger.info(f"[Collect][{chain_id}]: Повышение gasPrice до {current_gas_price} для {donor_address} (nonce {nonce}).")
                        tx['gasPrice'] = current_gas_price
        if not sent:
            logger.error(f"[Collect][{chain_id}]: Не удалось отправить TX с {donor_address} (nonce {nonce}) после нескольких попыток.")
        time.sleep(DELAY_BETWEEN_TX)
    logger.info(f"[Collect][{chain_id}]: Завершено. Собрано {len(collected_txs)} TX.")
    return len(collected_txs)

########################################
# 10. Функция сбора по выбранным сетям (Collect All)
########################################
def collect_all_networks(main_wallet, donor_wallets, selected_networks):
    overall_collected = {}
    for net in selected_networks:
        config = chain_info[net]
        logger.info(f"\n[Collect] Сеть: {net}")
        tx_count = collect_for_network(main_wallet, donor_wallets, config)
        overall_collected[net] = tx_count
    return overall_collected

########################################
# 11. Функции для получения балансов
########################################
def get_wallet_balances(wallets, networks):
    net_instances = {net: get_web3(cfg["rpc"]) for net, cfg in networks.items()}
    balances = {}
    for addr, _ in wallets:
        checksum = Web3.to_checksum_address(addr)
        balance_list = {}
        for net, w3_obj in net_instances.items():
            try:
                bal = w3_obj.eth.get_balance(checksum)
                bal_eth = float(w3_obj.from_wei(bal, "ether"))
            except Exception:
                bal_eth = 0
            balance_list[net] = bal_eth
        balances[addr] = balance_list
    return balances

def check_balances(wallets, networks):
    balances = get_wallet_balances(wallets, networks)
    for idx, (addr, _) in enumerate(wallets, start=1):
        bal_dict = balances.get(addr, {})
        bal_str = ", ".join(f"{net}: {bal:.6f} ETH" for net, bal in bal_dict.items())
        logger.info(f"Wallet {idx} ({addr}): Balances: {bal_str}")

########################################
# 12. Главное меню
########################################
def main():
    logger.info("Выберите режим работы:")
    logger.info("1 - Disperse: рассылка ETH от первого кошелька к остальным по выбранным сетям")
    logger.info("2 - Collect: сбор ETH с доноров к первому кошельку по выбранным сетям")
    mode = input("Введите 3 или 4: ").strip()

    wallets = load_wallets("wallets.txt")
    if len(wallets) < 2:
        logger.error("Необходимо минимум 2 кошелька (один отправитель/основной и минимум один получатель/донор).")
        exit(1)

    # Запрашиваем сеть или 'all'
    selected_network = input("Введите сеть (например, base, optimism, ink, и т.д.) или 'all' для всех: ").strip().lower()
    if selected_network == "all":
        selected_networks = list(chain_info.keys())
    else:
        if selected_network not in chain_info:
            logger.error(f"Сеть {selected_network} недоступна.")
            exit(1)
        selected_networks = [selected_network]

    if mode == "1":
        sender = wallets[0]
        recipients = wallets[1:]
        logger.info(f"[Disperse] Отправитель: {sender[0]}, получателей: {len(recipients)}")
        results = disperse_all_networks(sender, recipients) if "all" in selected_networks \
                  else {selected_networks[0]: disperse_for_network(sender, recipients, chain_info[selected_networks[0]])}
        logger.info("\n=== Итоговый отчет Disperse ===")
        for net, count in results.items():
            logger.info(f"{net}: успешно отправлено {count} TX")
    elif mode == "2":
        main_wallet = wallets[0]
        donors = wallets[1:]
        logger.info(f"[Collect] Основной кошелек: {main_wallet[0]}, доноров: {len(donors)}")
        results = collect_all_networks(main_wallet, donors, selected_networks)
        logger.info("\n=== Итоговый отчет Collect ===")
        for net, count in results.items():
            logger.info(f"{net}: успешно собрано {count} TX")
    else:
        logger.error("Неверный режим. Завершение работы.")
        exit(1)

    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()

import logging
import os
import time
import random
import requests
import concurrent.futures
from web3 import Web3
from eth_account import Account


########################################
# 1. Логирование (цветной форматтер)
########################################
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
# 2. Загрузка прокси из файла proxies.txt (если есть)
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
# 3. Функция создания и кэширования объектов Web3
########################################
WEB3_CACHE = {}


def get_web3(rpc):
    if rpc in WEB3_CACHE:
        return WEB3_CACHE[rpc]
    else:
        if PROXIES:
            proxy = random.choice(PROXIES)
            logger.debug(f"Используется прокси для Web3: {proxy}")
            provider = Web3.HTTPProvider(rpc, request_kwargs={"proxies": {"http": proxy, "https": proxy}})
        else:
            provider = Web3.HTTPProvider(rpc)
        w3_obj = Web3(provider)
        WEB3_CACHE[rpc] = w3_obj
        return w3_obj


########################################
# 4. Конфигурация блокчейнов (chain_info)
########################################
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'
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
# 5. Li.Fi API настройки
########################################
LI_FI_QUOTE_URL = "https://li.quest/v1/quote"
NATIVE_ETH = ZERO_ADDRESS
DEFAULT_AMOUNT_WEI = str(Web3.to_wei(0.0001, "ether"))


########################################
# 6. Загрузка кошельков (wallets.txt)
########################################
# Формат: address:private_key или address:private_key;proxy
def load_wallets(filename="wallets.txt"):
    if not os.path.exists(filename):
        logger.error("Файл wallets.txt не найден!")
        exit(1)
    with open(filename, "r") as f:
        lines = f.read().splitlines()
    wallets = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if ';' in line:
            main_part, proxy = line.split(';', 1)
            proxy = proxy.strip()
        else:
            main_part = line
            proxy = ""
        if ':' in main_part:
            addr, priv = main_part.split(':', 1)
            addr = addr.strip()
            priv = priv.strip()
        else:
            priv = main_part.strip()
            addr = Account.from_key(priv).address
        wallets.append((addr, priv, proxy))
    return wallets


########################################
# 7. Функция запроса котировки через li.fi API (GET)
########################################
def get_li_fi_quote(private_key, from_chain, to_chain, from_amount, proxies={}):
    account = Account.from_key(private_key)
    checksum_address = Web3.to_checksum_address(account.address)
    from_chain_id = chain_info[from_chain]['chain_id']
    to_chain_id = chain_info[to_chain]['chain_id']
    params = {
        "fromChain": from_chain_id,
        "toChain": to_chain_id,
        "fromToken": NATIVE_ETH,
        "toToken": NATIVE_ETH,
        "fromAmount": from_amount,
        "fromAddress": checksum_address
    }
    headers = {"Content-Type": "application/json"}
    if not proxies and PROXIES:
        chosen_proxy = random.choice(PROXIES)
        proxies = {'http': chosen_proxy, 'https': chosen_proxy}
        logger.info(f"(LI.Fi) Используется прокси для запроса котировки: {chosen_proxy}")
    try:
        logger.info(
            f"LI.Fi: Запрос котировки: fromChain={from_chain_id}, toChain={to_chain_id}, fromAmount={from_amount}, fromAddress={checksum_address}")
        r = requests.get(LI_FI_QUOTE_URL, params=params, headers=headers, proxies=proxies, timeout=30)
        if r.status_code == 200:
            data = r.json()
            logger.info(f"LI.Fi: Получена котировка для toChain {to_chain_id}")
            return data
        else:
            try:
                err_data = r.json()
                if all(k in err_data for k in ("errorType", "code", "message")):
                    err_msg = f'errorType: {err_data["errorType"]}, code: {err_data["code"]}, message: {err_data["message"]}'
                else:
                    err_msg = err_data.get("message", r.text)
            except Exception:
                err_msg = r.text
            logger.error(f"LI.Fi: HTTP ошибка для toChain {to_chain_id}: {r.status_code} - {err_msg}")
            return None
    except Exception as e:
        logger.error(f"LI.Fi: Ошибка при получении котировки для toChain {to_chain_id}: {str(e)}")
        return None


########################################
# 8. Функция отправки транзакции по данным котировки
########################################
def send_quote_transaction(quote_data, private_key, w3):
    if "transactionRequest" not in quote_data:
        logger.error("В котировке отсутствует 'transactionRequest'")
        return None
    tx_req = quote_data["transactionRequest"]
    try:
        to_address = tx_req["to"].strip()
        data_field = tx_req["data"].strip()
        value_int = int(tx_req["value"].strip(), 16)
        gas_int = int(tx_req["gasLimit"].strip(), 16)
        gas_price_int = int(tx_req["gasPrice"].strip(), 16)
        chain_id = tx_req["chainId"]
    except Exception as e:
        logger.error(f"Ошибка при разборе transactionRequest: {str(e)}")
        return None
    acct = Account.from_key(private_key)
    nonce = w3.eth.get_transaction_count(acct.address, "pending")
    tx = {
        "to": to_address,
        "data": data_field,
        "value": value_int,
        "gas": gas_int,
        "gasPrice": gas_price_int,
        "chainId": chain_id,
        "nonce": nonce
    }
    try:
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info(f"Транзакция отправлена: {w3.to_hex(tx_hash)}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        logger.info(f"Транзакция подтверждена, статус: {receipt.status}")
        return tx_hash
    except Exception as e:
        logger.error(f"Ошибка при отправке транзакции: {str(e)}")
        return None


########################################
# 9. Функция проверки балансов по всем сетям для каждого кошелька
########################################
def get_wallet_balances(wallets, networks):
    net_instances = {net: get_web3(cfg["rpc"]) for net, cfg in networks.items()}
    balances = {}
    for addr, _, _ in wallets:
        checksum = Web3.to_checksum_address(addr)
        balance_list = []
        for net, w3_obj in net_instances.items():
            try:
                bal = w3_obj.eth.get_balance(checksum)
                bal_eth = w3_obj.from_wei(bal, "ether")
                balance_list.append(f"{net} - {bal_eth:.6f} ETH")
            except Exception:
                balance_list.append(f"{net} - Error")
        balances[addr] = ", ".join(balance_list)
    return balances


########################################
# 10. Функция обработки одного кошелька (многопоточность)
########################################
def process_wallet(wallet_data, from_chain, to_chain_input, amount_wei):
    address, priv, proxy = wallet_data
    results = {}
    proxies = {'http': proxy, 'https': proxy} if proxy else {}
    try:
        logger.info(f"Начинаю мост для кошелька {address} из {from_chain}")
        # Получаем локальный объект Web3 для from_chain
        w3_local = get_web3(chain_info[from_chain]["rpc"])
        if to_chain_input == "all":
            for target in chain_info.keys():
                if target == from_chain:
                    continue
                logger.info(f"Мост из {from_chain} в {target} для {address}")
                quote = get_li_fi_quote(priv, from_chain, target, amount_wei, proxies=proxies)
                if quote is None:
                    results[f"{address}->{target}"] = "Quote Error"
                else:
                    # Проверяем баланс: вычисляем требуемую сумму
                    try:
                        tx_req = quote["transactionRequest"]
                        gas_limit = int(tx_req["gasLimit"].strip(), 16)
                        gas_price = int(tx_req["gasPrice"].strip(), 16)
                        tx_value = int(tx_req["value"].strip(), 16)
                        required = tx_value + gas_limit * gas_price
                        current_balance = w3_local.eth.get_balance(Web3.to_checksum_address(address))
                        if current_balance < required:
                            logger.error(
                                f"Кошелек {address} имеет недостаточно средств. Баланс: {current_balance}, требуется: {required}")
                            results[f"{address}->{target}"] = "FAILED (Insufficient funds)"
                            continue
                    except Exception as e:
                        logger.error(f"Ошибка расчёта необходимых средств для {address} -> {target}: {e}")
                        results[f"{address}->{target}"] = "FAILED (Calc error)"
                        continue

                    tx_hash = send_quote_transaction(quote, priv, w3_local)
                    results[f"{address}->{target}"] = "Tx Successful" if tx_hash else "Tx Error"
        else:
            logger.info(f"Мост из {from_chain} в {to_chain_input} для {address}")
            quote = get_li_fi_quote(priv, from_chain, to_chain_input, amount_wei, proxies=proxies)
            if quote is None:
                results[address] = "Quote Error"
            else:
                try:
                    tx_req = quote["transactionRequest"]
                    gas_limit = int(tx_req["gasLimit"].strip(), 16)
                    gas_price = int(tx_req["gasPrice"].strip(), 16)
                    tx_value = int(tx_req["value"].strip(), 16)
                    required = tx_value + gas_limit * gas_price
                    current_balance = w3_local.eth.get_balance(Web3.to_checksum_address(address))
                    if current_balance < required:
                        logger.error(
                            f"Кошелек {address} имеет недостаточно средств. Баланс: {current_balance}, требуется: {required}")
                        results[address] = "FAILED (Insufficient funds)"
                        return results
                except Exception as e:
                    logger.error(f"Ошибка расчёта необходимых средств для {address}: {e}")
                    results[address] = "FAILED (Calc error)"
                    return results

                tx_hash = send_quote_transaction(quote, priv, w3_local)
                results[address] = "Tx Successful" if tx_hash else "Tx Error"
    except Exception as err:
        logger.error(f"Ошибка для {address}: {err}")
        results[address] = "Error"
    return results


########################################
# 11. Основная функция main()
########################################
def main():
    available_chains = list(chain_info.keys())
    logger.info("Доступные блокчейны: " + ", ".join(available_chains))

    from_chain = input("Введите блокчейн отправления: ").strip().lower()
    if from_chain not in chain_info:
        logger.error("Блокчейн отправления недоступен!")
        return

    to_chain_input = input("Введите блокчейн назначения (или 'all' для всех остальных): ").strip().lower()
    if to_chain_input != "all" and to_chain_input not in chain_info:
        logger.error("Блокчейн назначения недоступен!")
        return

    amount_eth = input("Введите сумму перевода в ETH: ").strip()
    try:
        amount_wei = str(Web3.to_wei(float(amount_eth), "ether"))
    except Exception as e:
        logger.error(f"Ошибка конвертации суммы: {e}")
        return

    wallets = load_wallets()
    if not wallets:
        logger.error("Файл wallets.txt пуст!")
        return

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {
            executor.submit(process_wallet, wallet, from_chain, to_chain_input, amount_wei): wallet
            for wallet in wallets
        }
        for future in concurrent.futures.as_completed(future_map):
            partial_res = future.result()
            results.update(partial_res)

    balances = get_wallet_balances(wallets, chain_info)

    logger.info("\n=== Итоговый отчёт ===")
    wallet_index_map = {wallets[i][0]: i + 1 for i in range(len(wallets))}
    addresses_in_order = [w[0] for w in wallets]
    for addr in addresses_in_order:
        relevant_keys = [k for k in results if k.startswith(addr)]
        statuses = [results[rk] for rk in relevant_keys]
        if statuses and any(s == "Tx Successful" for s in statuses):
            overall = "SUCCESS"
        else:
            overall = "FAILED"
        idx = wallet_index_map.get(addr, "?")
        bal_str = balances.get(addr, "Нет данных о балансе")
        logger.info(f"Wallet {idx} ({addr}): {overall}")
        logger.info(f"  Balances: {bal_str}")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()

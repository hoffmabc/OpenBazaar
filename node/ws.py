import threading
import logging
import subprocess
import pycountry
import gnupg
import obelisk
import json
import random
import time
import urllib2
from bitcoin import (
    apply_multisignatures,
    mk_multisig_script,
    mktx,
    multisign,
    scriptaddr
)
from tornado import iostream
import tornado.websocket
from twisted.internet import reactor
from node import constants, protocol, trust
from node.backuptool import BackupTool, Backup, BackupJSONEncoder
import bitcoin


class ProtocolHandler(object):
    def __init__(self, websocket_handler):

        self.market = websocket_handler.application.market
        self.transport = websocket_handler.application.transport
        self.handler = websocket_handler
        self.db_connection = websocket_handler.application.db

        self.transport.set_websocket_handler(self)

        self.all_messages = (
            'peer',
            'page',
            'peer_remove',
            'node_page',
            'listing_results',
            'listing_result',
            'no_listing_result',
            'release_funds_tx',
            'all'
        )

        # register on transport events to forward..
        self.transport.add_callbacks([
            (
                msg,
                {
                    'cb': getattr(self, 'on_%s' % msg),
                    'validator_cb': getattr(self, 'validate_on_%s' % msg)
                }
            )
            for msg in self.all_messages
        ])

        # handlers from events coming from websocket, we shouldnt need this
        self._handlers = {
            "load_page": self.client_load_page,
            "connect": self.client_connect,
            "peers": self.client_peers,
            "query_page": self.client_query_page,
            "review": self.client_review,
            "order": self.client_order,
            "search": self.client_query_network_products,
            "shout": self.client_shout,
            "get_notaries": self.client_get_notaries,
            "add_trusted_notary": self.client_add_trusted_notary,
            "add_node": self.client_add_guid,
            "remove_trusted_notary": self.client_remove_trusted_notary,
            "query_store_products": self.client_query_store_products,
            "check_order_count": self.client_check_order_count,
            "check_inbox_count": self.client_check_inbox_count,
            "query_orders": self.client_query_orders,
            "query_contracts": self.client_query_contracts,
            "stop_server": self.client_stop_server,
            "query_messages": self.client_query_messages,
            "send_message": self.client_send_message,
            "send_inbox_message": self.client_send_inbox_message,
            "get_inbox_messages": self.client_get_inbox_messages,
            "get_inbox_sent_messages": self.client_get_inbox_sent_messages,
            "get_btc_ticker": self.client_get_btc_ticker,
            "update_settings": self.client_update_settings,
            "query_order": self.client_query_order,
            "pay_order": self.client_pay_order,
            "ship_order": self.client_ship_order,
            "release_payment": self.client_release_payment,
            "refund_order": self.client_refund_order,
            "remove_contract": self.client_remove_contract,
            "generate_secret": self.client_generate_secret,
            "welcome_dismissed": self.client_welcome_dismissed,
            "republish_contracts": self.client_republish_contracts,
            "import_raw_contract": self.client_import_raw_contract,
            "create_contract": self.client_create_contract,
            "update_contract": self.client_update_contract,
            "clear_dht_data": self.client_clear_dht_data,
            "clear_peers_data": self.client_clear_peers_data,
            "read_log": self.client_read_log,
            "create_backup": self.client_create_backup,
            "get_backups": self.get_backups,
            "undo_remove_contract": self.client_undo_remove_contract,
            "refresh_settings": self.client_refresh_settings,
            "refund_recipient": self.client_refund_recipient,
        }

        self.timeouts = []

        self.log = logging.getLogger(
            '[%s] %s' % (self.transport.market_id, self.__class__.__name__)
        )

    def validate_on_page(self, *data):
        self.log.debug('Validating on page message.')
        # data = data[0]
        # keys = ("senderGUID")
        return True

    def on_page(self, page):

        guid = page.get('senderGUID')
        avatar_url = page.get('avatar_url')
        self.log.info(page)

        sin = page.get('sin')

        self.log.info("Received store info from node: %s", page)

        if sin and page:
            self.market.pages[sin] = page

        self.transport.update_avatar(guid, avatar_url)

        # TODO: allow async calling in different thread
        def reputation_pledge_retrieved(amount, page):
            self.log.debug(
                'Received reputation pledge amount %s for guid %s',
                amount, guid
            )
            bitcoins = float(amount) / constants.SATOSHIS_IN_BITCOIN
            bitcoins = round(bitcoins, 4)
            self.market.pages[sin]['reputation_pledge'] = bitcoins
            self.send_to_client(
                None, {
                    'type': 'reputation_pledge_update',
                    'value': bitcoins,
                    'v': constants.VERSION
                }
            )

        trust.get_global(
            guid,
            lambda amount, page=page: reputation_pledge_retrieved(amount, page)
        )

    def client_refresh_settings(self, socket_handler, msg):
        self.log.debug('Refreshing user settings')
        self.send_opening()

    def client_refund_recipient(self, socket_handler, msg):
        self.log.debug('Refunding recipient: %s', msg)
        self.refund_recipient(msg.get('recipientId'), msg.get('orderId'))

    def refund_recipient(self, recipient_id, order_id):
        # Get Order
        order = self.market.orders.get_order(order_id)

        contract = order['signed_contract_body']

        # Find Seller Data in Contract
        offer_data = ''.join(contract.split('\n')[8:])
        index_of_seller_signature = offer_data.find(
            '- - -----BEGIN PGP SIGNATURE-----', 0, len(offer_data)
        )
        offer_data_json = offer_data[:index_of_seller_signature]
        offer_data_json = json.loads(offer_data_json)
        self.log.info('Offer Data: %s', offer_data_json)

        # Find Buyer Data in Contract
        bid_data_index = offer_data.find(
            '"Buyer"', index_of_seller_signature, len(offer_data)
        )
        end_of_bid_index = offer_data.find(
            '- -----BEGIN PGP SIGNATURE', bid_data_index, len(offer_data)
        )
        bid_data_json = "{"
        bid_data_json += offer_data[bid_data_index:end_of_bid_index]
        bid_data_json = json.loads(bid_data_json)

        # Find Notary Data in Contract
        notary_data_index = offer_data.find(
            '"Notary"', end_of_bid_index, len(offer_data)
        )
        end_of_notary_index = offer_data.find(
            '-----BEGIN PGP SIGNATURE', notary_data_index, len(offer_data)
        )
        notary_data_json = "{"
        notary_data_json += offer_data[notary_data_index:end_of_notary_index]
        notary_data_json = json.loads(notary_data_json)

        try:
            client = obelisk.ObeliskOfLightClient(
                'tcp://%s' % self.transport.settings['obelisk']
            )

            seller = offer_data_json['Seller']
            buyer = bid_data_json['Buyer']
            notary = notary_data_json['Notary']

            pubkeys = [
                seller['seller_BTC_uncompressed_pubkey'],
                buyer['buyer_BTC_uncompressed_pubkey'],
                notary['notary_BTC_uncompressed_pubkey']
            ]

            script = mk_multisig_script(pubkeys, 2, 3)
            multi_address = scriptaddr(script)

            def get_history_callback(escrow, history, order):

                private_key = self.get_signing_key(order_id)

                if escrow is not None:
                    self.log.error("Error fetching history: %s", escrow)
                    # TODO: Send error message to GUI
                    return

                # Create unsigned transaction
                unspent = [row[:4] for row in history if row[4] is None]

                # Send all unspent outputs (everything in the address) minus
                # the fee
                total_amount = 0
                inputs = []
                for row in unspent:
                    assert len(row) == 4, 'Obelisk returned a wonky row'
                    inputs.append("%s:%s" % (row[0].encode('hex'), row[1]))
                    value = row[3]
                    total_amount += value

                # Constrain fee so we don't get negative amount to send
                network_fee = min(total_amount, 10000)
                send_amount = total_amount - network_fee

                # Notary Fee (% of post-network fee amount)
                notary_fee = int((float(notary['notary_fee'])/100) * send_amount)
                notary_address = notary.get('notary_refund_addr')

                # Amount to Refund to User(s)
                refund_amount = max(send_amount-notary_fee, 0)

                self.log.debug('Notary Fee: %s satoshis', notary_fee)
                self.log.debug('Recipient Will Get: %s satoshis', refund_amount)

                if recipient_id == 1:
                    recipient_guid = buyer.get('buyer_GUID')
                    recipient_address = buyer.get('buyer_refund_addr')
                else:
                    recipient_guid = seller.get('seller_GUID')
                    recipient_address = seller.get('seller_refund_addr')

                transaction = mktx(inputs, [
                    "%s:%s" % (recipient_address, refund_amount),
                    "%s:%s" % (notary_address, notary_fee)
                ])

                signatures = [multisign(transaction, x, script, private_key)
                              for x in range(len(inputs))]

                self.market.release_funds_to_recipient(
                    buyer['buyer_order_id'], transaction, script, signatures,
                    recipient_guid, buyer.get('buyer_GUID'), refund=recipient_id
                )

            def get_history():
                client.fetch_history(
                    multi_address,
                    lambda escrow, history, order=order: get_history_callback(escrow, history, order))

            reactor.callFromThread(get_history)

        except Exception as exc:
            self.log.error('%s', exc)

    def send_opening(self):
        peers = self.get_peers()

        country_codes = []
        for country in pycountry.countries:
            country_codes.append({"code": country.alpha2, "name": country.name})

        settings = self.market.get_settings()

        message = {
            'type': 'myself',
            'pubkey': settings.get('pubkey'),
            'peers': peers,
            'settings': settings,
            'guid': self.transport.guid,
            # 'sin': self.transport.sin,
            # 'uri': self.transport.uri,
            'countryCodes': country_codes,
            'v': constants.VERSION
        }

        self.send_to_client(None, message)

        burn_addr = trust.burnaddr_from_guid(self.transport.guid)

        def found_unspent(amount):
            self.send_to_client(None, {
                'type': 'burn_info_available',
                'amount': amount,
                'addr': burn_addr,
                'v': constants.VERSION
            })

        trust.get_unspent(burn_addr, found_unspent)

    def client_read_log(self, socket_handler, msg):
        self.market.p = subprocess.Popen(
            ["tail", "-f", "logs/development.log", "logs/production.log"],
            stdout=subprocess.PIPE)

        self.stream = iostream.PipeIOStream(
            self.market.p.stdout.fileno()
        )
        self.stream.read_until("\n", self.line_from_nettail)

    def line_from_nettail(self, data):
        self.send_to_client(None, {"type": "log_output", "line": data})
        self.stream.read_until("\n", self.line_from_nettail)

    def validate_on_listing_results(self, *data):
        self.log.debug('Validating on listing results message.')
        return "contracts" in data

    def on_listing_results(self, msg):
        self.log.datadump('Found results %s', msg)
        self.send_to_client(None, {
            "type": "store_contracts",
            "products": msg['contracts']
        })

    def validate_on_no_listing_result(self, *data):
        self.log.debug('Validating on no listing result message.')
        return True

    def on_no_listing_result(self, msg):
        self.log.debug('No listings found')
        self.send_to_client(None, {
            "type": "no_listings_found"
        })

    def validate_on_listing_result(self, *data):
        self.log.debug('Validating on listing result message.')
        return True

    def on_listing_result(self, msg):
        self.log.datadump('Found result %s', msg)
        self.send_to_client(None, {
            "type": "store_contract",
            "contract": msg
        })

    def client_stop_server(self, socket_handler, msg):
        self.log.error('Killing OpenBazaar')
        self.market_application.shutdown()

    def client_load_page(self, socket_handler, msg):
        self.send_to_client(None, {"type": "load_page"})

    def client_add_trusted_notary(self, socket_handler, msg):
        self.log.info('Adding trusted notary %s', msg)
        self.market.add_trusted_notary(msg.get('guid'), msg.get('nickname'))

    def client_add_guid(self, socket_handler, msg):
        self.log.info('Adding node by guid %s', msg)

        def get_peers_callback(msg):
            self.get_peers()

        self.transport.dht.iterative_find_node(msg.get('guid'), get_peers_callback)

    def client_remove_trusted_notary(self, socket_handler, msg):
        self.log.info('Removing trusted notary %s', msg)
        self.market.remove_trusted_notary(msg.get('guid'))

    def client_get_notaries(self, socket_handler, msg):
        self.log.debug('Retrieving notaries')
        notaries = self.market.get_notaries()
        self.log.debug('Getting notaries %s', notaries)
        self.send_to_client(None, {
            "type": "settings_notaries",
            "notaries": notaries
        })

    def client_clear_dht_data(self, socket_handler, msg):
        self.log.debug('Clearing DHT Data')
        self.db_connection.delete_entries("datastore")

    def client_clear_peers_data(self, socket_handler, msg):
        self.log.debug('Clearing Peers Data')
        self.db_connection.delete_entries("peers")

    # Requests coming from the client
    def client_connect(self, socket_handler, msg):
        self.log.info("Connection command: %s", msg)
        self.transport.connect(msg['uri'], lambda x: None)
        self.send_ok()

    def client_peers(self, socket_handler, msg):
        self.log.info("Peers command")
        self.send_to_client(None, {"type": "peers", "peers": self.get_peers()})

    def client_welcome_dismissed(self, socket_handler, msg):
        self.market.disable_welcome_screen()

    def client_undo_remove_contract(self, socket_handler, msg):
        self.market.undo_remove_contract(msg.get('contract_id'))

    def client_check_order_count(self, socket_handler, msg):
        self.log.debug('Checking order count')
        orders = self.db_connection.select_entries(
            "orders",
            {
                "market_id": self.transport.market_id,
                "state": "Waiting for Payment"
            },
            select_fields="order_id"
        )

        self.send_to_client(
            None,
            {"type": "order_count", "count": len(orders)}
        )

    def client_check_inbox_count(self, socket_handler, msg):
        self.log.debug('Checking inbox count')
        self.market.check_inbox_count()

    def refresh_peers(self):
        self.log.info("Peers command")
        self.send_to_client(None, {"type": "peers", "peers": self.get_peers()})

    def client_query_page(self, socket_handler, msg):
        find_guid = msg['findGUID']
        self.log.info('Looking for Store: %s', find_guid)

        query_id = random.randint(0, 1000000)
        self.timeouts.append(query_id)

        def log_callback(msg, query_id):
            self.log.info('Received a query page response: %s', query_id)

        self.market.query_page(
            find_guid,
            lambda msg, query_id=query_id: log_callback(msg, query_id)
        )

    def client_query_orders(self, socket_handler=None, msg=None):

        self.log.info("Querying for Orders %s", msg)

        if 'page' in msg:
            page = msg['page']
        else:
            page = 0

        if msg is not None and 'merchant' in msg:
            if msg['merchant'] == 1:
                orders = self.market.orders.get_orders(page, True)
            elif msg['merchant'] == 2:
                orders = self.market.orders.get_orders(
                    page, merchant=None, notarizations=True
                )
            else:
                orders = self.market.orders.get_orders(page, merchant=False)
        else:
            orders = self.market.orders.get_orders(page)

        self.send_to_client(None, {
            "type": "myorders",
            "page": page,
            "total": orders['total'],
            "orders": orders['orders']
        })

    def client_query_contracts(self, socket_handler, msg):

        self.log.info("Querying for Contracts")

        page = msg['page'] if 'page' in msg else 0
        contracts = self.market.get_contracts(page)

        self.send_to_client(None, {
            "type": "contracts",
            "contracts": contracts
        })

    def client_query_messages(self, socket_handler, msg):

        self.log.info("Querying for Messages")

        # Query bitmessage for messages
        messages = self.market.get_messages()
        self.log.info('Bitmessages: %s', messages)

        self.send_to_client(None, {"type": "messages", "messages": messages})

    def client_send_message(self, socket_handler, msg):

        self.log.info("Sending message")

        # Send message with market's bitmessage
        self.market.send_message(msg)

    def client_send_inbox_message(self, socket_handler, msg):

        self.log.info("Sending internal message")
        self.market.send_inbox_message(msg)

    def client_get_inbox_messages(self, socket_handler, msg):

        self.log.info("Getting inbox messages")
        messages = self.market.get_inbox_messages()
        self.send_to_client(None, {"type": "inbox_messages", "messages": messages})

    def client_get_inbox_sent_messages(self, socket_handler, msg):

        self.log.info("Getting inbox sent messages")
        messages = self.market.get_inbox_sent_messages()
        self.send_to_client(None, {"type": "inbox_sent_messages", "messages": messages})

    def client_get_btc_ticker(self, socket_handler, msg):
        self.log.info('Get BTC Ticker')
        url = 'https://blockchain.info/ticker'

        def get_ticker():

            try:
                usock = urllib2.urlopen(url)
                data = usock.read()
                usock.close()
            except Exception as usock_exception:
                self.log.error('Cannot retrieve ticker info: %s', usock_exception.message)
                return

            self.send_to_client(None, {
                'type': 'btc_ticker',
                'data': data
            })

        threading.Thread(target=get_ticker).start()

    def client_republish_contracts(self, socket_handler, msg):
        self.log.info("Republishing contracts")
        self.market.republish_contracts()

    def client_import_raw_contract(self, socket_handler, contract):
        self.log.info(
            "Importing New Contract "
            "(NOT IMPLEMENTED! TODO: Market.import_contract(contract)"
        )

    # Get a single order's info
    def client_query_order(self, socket_handler, msg):
        order = self.market.orders.get_order(msg['orderId'])
        self.send_to_client(None, {"type": "orderinfo", "order": order})

    def client_update_settings(self, socket_handler, msg):
        self.send_to_client(None, {"type": "settings", "values": msg})
        if msg['settings'].get('btc_pubkey'):
            del msg['settings']['btc_pubkey']
        self.market.save_settings(msg['settings'])

    def client_create_contract(self, socket_handler, contract):
        self.log.datadump('New Contract: %s', contract)
        self.market.save_contract(contract)

    def client_update_contract(self, socket_handler, msg):
        contract_id = msg.get('contract_id')
        contract = msg.get('contract')
        self.log.datadump('New Contract: %s', contract)
        self.market.save_contract(contract, contract_id)

    def client_remove_contract(self, socket_handler, msg):
        self.log.info("Remove contract: %s", msg)
        self.market.remove_contract(msg)

    def client_pay_order(self, socket_handler, msg):

        self.log.info("Marking Order as Paid: %s", msg)
        order = self.market.orders.get_order(msg['orderId'])

        order['shipping_address'] = self.market.shipping_address()

        # Send to exchange partner
        self.market.orders.pay_order(order, msg['orderId'])

    def client_ship_order(self, socket_handler, msg):

        self.log.info("Shipping order out: %s", msg)

        order = self.market.orders.get_order(msg['orderId'])

        # Send to exchange partner
        self.market.orders.ship_order(
            order, msg['orderId'], msg['paymentAddress']
        )

    def client_refund_order(self, socket_handler, msg):
        self.log.info('Refunding payment and cancelling order')

        # Get Order
        order = self.market.orders.get_order(msg['orderId'])

        contract = order['signed_contract_body']

        # Find Seller Data in Contract
        offer_data = ''.join(contract.split('\n')[8:])
        index_of_seller_signature = offer_data.find(
            '- - -----BEGIN PGP SIGNATURE-----', 0, len(offer_data)
        )
        offer_data_json = offer_data[:index_of_seller_signature]
        offer_data_json = json.loads(offer_data_json)
        self.log.info('Offer Data: %s', offer_data_json)

        # Find Buyer Data in Contract
        bid_data_index = offer_data.find(
            '"Buyer"', index_of_seller_signature, len(offer_data)
        )
        end_of_bid_index = offer_data.find(
            '- -----BEGIN PGP SIGNATURE', bid_data_index, len(offer_data)
        )
        bid_data_json = "{"
        bid_data_json += offer_data[bid_data_index:end_of_bid_index]
        bid_data_json = json.loads(bid_data_json)

        # Find Notary Data in Contract
        notary_data_index = offer_data.find(
            '"Notary"', end_of_bid_index, len(offer_data)
        )
        end_of_notary_index = offer_data.find(
            '-----BEGIN PGP SIGNATURE', notary_data_index, len(offer_data)
        )
        notary_data_json = "{"
        notary_data_json += offer_data[notary_data_index:end_of_notary_index]
        notary_data_json = json.loads(notary_data_json)

        try:
            client = obelisk.ObeliskOfLightClient(
                'tcp://%s' % self.transport.settings['obelisk']
            )

            seller = offer_data_json['Seller']
            buyer = bid_data_json['Buyer']
            notary = notary_data_json['Notary']

            pubkeys = [
                seller['seller_BTC_uncompressed_pubkey'],
                buyer['buyer_BTC_uncompressed_pubkey'],
                notary['notary_BTC_uncompressed_pubkey']
            ]

            script = mk_multisig_script(pubkeys, 2, 3)
            multi_address = scriptaddr(script)

            def get_history_callback(escrow, history, order):

                private_key = self.get_signing_key(msg['orderId'])

                if escrow is not None:
                    self.log.error("Error fetching history: %s", escrow)
                    # TODO: Send error message to GUI
                    return

                # Create unsigned transaction
                unspent = [row[:4] for row in history if row[4] is None]

                # Send all unspent outputs (everything in the address) minus
                # the fee
                total_amount = 0
                inputs = []
                for row in unspent:
                    assert len(row) == 4, 'Obelisk returned a wonky row'
                    inputs.append("%s:%s" % (row[0].encode('hex'), row[1]))
                    value = row[3]
                    total_amount += value

                # Constrain fee so we don't get negative amount to send
                fee = min(total_amount, 10000)
                send_amount = total_amount - fee

                payment_output = order['payment_address']
                transaction = mktx(inputs, ["%s:%s" % (payment_output, send_amount)])

                signatures = [multisign(transaction, x, script, private_key)
                              for x in range(len(inputs))]

                self.market.release_funds_to_recipient(
                    buyer['buyer_order_id'], transaction, script, signatures,
                    order.get('merchant')
                )

            def get_history():
                client.fetch_history(
                    multi_address,
                    lambda escrow, history, order=order: get_history_callback(escrow, history, order))

            reactor.callFromThread(get_history)

        except Exception as exc:
            self.log.error('%s', exc)

    def get_signing_key(self, order_id):
        # Get BIP32 child signing key for this order id
        rows = self.db_connection.select_entries("keystore", {
            'order_id': order_id
        })

        if len(rows):
            key_id = rows[0]['id']

            settings = self.transport.settings

            wallet = bitcoin.bip32_ckd(bitcoin.bip32_master_key(settings.get('bip32_seed')), 1)
            wallet_chain = bitcoin.bip32_ckd(wallet, 0)
            bip32_identity_priv = bitcoin.bip32_ckd(wallet_chain, key_id)
            # bip32_identity_pub = bitcoin.bip32_privtopub(bip32_identity_priv)
            return bitcoin.encode_privkey(bitcoin.bip32_extract_key(bip32_identity_priv), 'wif')

        else:
            self.log.error('No keys found for that contract id: #%s', order_id)
            return

    def get_signing_key_by_contract_id(self, contract_id):
        # Get BIP32 child signing key for this order id
        rows = self.db_connection.select_entries("keystore", {
            'contract_id': contract_id
        })

        if len(rows):
            key_id = rows[0]['id']

            settings = self.transport.settings

            wallet = bitcoin.bip32_ckd(bitcoin.bip32_master_key(settings.get('bip32_seed')), 1)
            wallet_chain = bitcoin.bip32_ckd(wallet, 0)
            bip32_identity_priv = bitcoin.bip32_ckd(wallet_chain, key_id)
            # bip32_identity_pub = bitcoin.bip32_privtopub(bip32_identity_priv)
            return bitcoin.encode_privkey(bitcoin.bip32_extract_key(bip32_identity_priv), 'wif')

        else:
            self.log.error('No keys found for that contract id: #%s', contract_id)
            return

    def client_release_payment(self, socket_handler, msg):
        self.log.info('Releasing payment to Merchant %s', msg)
        self.log.info('Using Obelisk at tcp://%s', self.transport.settings['obelisk'])

        order = self.market.orders.get_order(msg['orderId'])
        contract = order['signed_contract_body']

        # Find Seller Data in Contract
        offer_data = ''.join(contract.split('\n')[8:])
        index_of_seller_signature = offer_data.find(
            '- - -----BEGIN PGP SIGNATURE-----', 0, len(offer_data)
        )
        offer_data_json = offer_data[0:index_of_seller_signature]
        offer_data_json = json.loads(offer_data_json)
        self.log.info('Offer Data: %s', offer_data_json)

        # Find Buyer Data in Contract
        bid_data_index = offer_data.find(
            '"Buyer"', index_of_seller_signature, len(offer_data)
        )
        end_of_bid_index = offer_data.find(
            '- -----BEGIN PGP SIGNATURE', bid_data_index, len(offer_data)
        )
        bid_data_json = "{"
        bid_data_json += offer_data[bid_data_index:end_of_bid_index]
        bid_data_json = json.loads(bid_data_json)

        # Find Notary Data in Contract
        notary_data_index = offer_data.find(
            '"Notary"', end_of_bid_index, len(offer_data)
        )
        end_of_notary_index = offer_data.find(
            '-----BEGIN PGP SIGNATURE', notary_data_index, len(offer_data)
        )
        notary_data_json = "{"
        notary_data_json += offer_data[notary_data_index:end_of_notary_index]
        notary_data_json = json.loads(notary_data_json)
        self.log.info('Notary Data: %s', notary_data_json)

        try:
            client = obelisk.ObeliskOfLightClient(
                'tcp://%s' % self.transport.settings['obelisk']
            )

            seller = offer_data_json['Seller']
            buyer = bid_data_json['Buyer']
            notary = notary_data_json['Notary']

            pubkeys = [
                seller['seller_BTC_uncompressed_pubkey'],
                buyer['buyer_BTC_uncompressed_pubkey'],
                notary['notary_BTC_uncompressed_pubkey']
            ]
            self.log.debug('Pubkeys: %s', pubkeys)

            script = mk_multisig_script(pubkeys, 2, 3)
            multi_address = scriptaddr(script)

            def get_history_callback(escrow, history, order):

                private_key = self.get_signing_key(msg['orderId'])
                self.log.debug('private key %s', msg)

                if escrow is not None:
                    self.log.error("Error fetching history: %s", escrow)
                    # TODO: Send error message to GUI
                    return

                # Create unsigned transaction
                unspent = [row[:4] for row in history if row[4] is None]
                self.log.debug('Unspent Inputs: %s', unspent)

                # Send all unspent outputs (everything in the address) minus
                # the fee
                total_amount = 0
                inputs = []
                for row in unspent:
                    assert len(row) == 4
                    inputs.append(
                        str(row[0].encode('hex')) + ":" + str(row[1])
                    )
                    value = row[3]
                    total_amount += value

                # Constrain fee so we don't get negative amount to send
                fee = min(total_amount, 10000)
                send_amount = total_amount - fee

                if send_amount == 0:
                    self.log.debug('No money in this address any longer.')
                    return

                self.log.debug('Total amount to release to merchant: %s ', send_amount)

                # Get buyer signatures on inputs
                buyer_signatures = []
                self.log.debug('merchant tx %s, merchant script: %s', order['merchant_tx'],
                               order['merchant_script'])
                for i in range(0, len(inputs)):
                    signed_input = multisign(order['merchant_tx'], i, order['merchant_script'], private_key)
                    buyer_signatures.append(signed_input)

                merchant_sigs = order['merchant_sigs']
                merchant_sigs = merchant_sigs.encode('ascii')
                merchant_sigs = json.loads(merchant_sigs)

                # Apply signatures to mulsignature tx script
                self.log.debug('TX: %s', order)
                self.log.debug('Buyer Sigs: %s', buyer_signatures)
                self.log.debug('Merchant Sigs: %s', order['merchant_sigs'])
                self.log.debug('Script: %s', script)

                transaction = order['merchant_tx']

                for i in range(0, len(inputs)):
                    transaction = apply_multisignatures(
                        transaction, i, order['merchant_script'], merchant_sigs[i], buyer_signatures[i]
                    )

                self.log.debug('Broadcast TX to network: %s', transaction)
                result = bitcoin.pushtx(transaction)
                self.log.debug('BCI result: %s', result)

                if result == 'Transaction Submitted':

                    # Update database
                    self.db_connection.update_entries("orders", {
                        'state': 'Completed'
                    }, {
                        'order_id': msg['orderId']
                    })


            def get_history():
                self.log.debug('Getting history')

                client.fetch_history(
                    multi_address,
                    lambda escrow, history, order=order: get_history_callback(escrow, history, order)
                )

            reactor.callFromThread(get_history)

        except Exception as exc:
            self.log.error('%s', exc)

    def validate_on_release_funds_tx(self, *data):
        self.log.debug('Validating on release funds tx message. %s', data)
        return True

    def on_release_funds_tx(self, msg):

        self.log.info('Receiving signed tx from buyer %s', msg)

        recipient_id = int(msg.get('refund'))

        if recipient_id == 0 or recipient_id == 2:
            buyer_order_id = "%s-%s" % (msg.get('buyer_id'), msg.get('buyer_order_id'))

            if recipient_id == 2:
                order = self.market.orders.get_order(buyer_order_id, by_buyer_id=True)
            else:
                order = self.market.orders.get_order(buyer_order_id, by_buyer_id=True)
                signing_key = self.get_signing_key(order.get('order_id'))

        else:
            order = self.market.orders.get_order(msg.get('buyer_order_id'))
            signing_key = self.get_signing_key(order.get('order_id'))

        contract = order['signed_contract_body']

        # Find Seller Data in Contract
        offer_data = ''.join(contract.split('\n')[8:])
        index_of_seller_signature = offer_data.find(
            '- - -----BEGIN PGP SIGNATURE-----', 0, len(offer_data)
        )
        offer_data_json = offer_data[0:index_of_seller_signature]
        offer_data_json = json.loads(offer_data_json)
        self.log.info('Offer Data: %s', offer_data_json)

        if recipient_id == 2:
            signing_key = self.get_signing_key_by_contract_id(offer_data_json['Seller']['seller_contract_id'])

        # Find Buyer Data in Contract
        bid_data_index = offer_data.find(
            '"Buyer"', index_of_seller_signature, len(offer_data)
        )
        end_of_bid_index = offer_data.find(
            '- -----BEGIN PGP SIGNATURE', bid_data_index, len(offer_data)
        )

        # Find Notary Data in Contract
        notary_data_index = offer_data.find(
            '"Notary"', end_of_bid_index, len(offer_data)
        )
        end_of_notary_index = offer_data.find(
            '-----BEGIN PGP SIGNATURE', notary_data_index, len(offer_data)
        )
        notary_data_json = "{"
        notary_data_json += offer_data[notary_data_index:end_of_notary_index]
        notary_data_json = json.loads(notary_data_json)
        self.log.info('Notary Data: %s', notary_data_json)

        try:
            client = obelisk.ObeliskOfLightClient(
                'tcp://%s' % self.transport.settings['obelisk']
            )

            script = msg['script']
            multi_addr = scriptaddr(script)

            def get_history_callback(escrow, history, order):

                transaction = msg['tx']

                if escrow is not None:
                    self.log.error("Error fetching history: %s", escrow)
                    # TODO: Send error message to GUI
                    return

                unspent = [row[:4] for row in history if row[4] is None]

                # Send all unspent outputs (everything in the address) minus
                # the fee
                inputs = []
                for row in unspent:
                    assert len(row) == 4
                    inputs.append(
                        str(row[0].encode('hex')) + ":" + str(row[1])
                    )

                seller_signatures = []

                for inpt in range(0, len(inputs)):
                    mltsgn = multisign(
                        transaction, inpt, script, signing_key
                    )
                    print 'seller sig', mltsgn
                    seller_signatures.append(mltsgn)

                for i in range(0, len(inputs)):
                    transaction = apply_multisignatures(
                        transaction, i, script, seller_signatures[i], msg['signatures'][i]
                    )

                print 'FINAL SCRIPT: %s' % transaction
                print 'Sent', bitcoin.pushtx(transaction)

                self.send_to_client(
                    None,
                    {
                        "type": "order_notify",
                        "msg": "Funds were released for your sale."
                    }
                )

            def get_history():
                client.fetch_history(
                    multi_addr,
                    lambda escrow, history, order=order: get_history_callback(escrow, history, order)
                )

            reactor.callFromThread(get_history)

        except Exception as exc:
            self.log.error('%s', exc)

    def client_generate_secret(self, socket_handler, msg):
        self.transport._generate_new_keypair()
        self.send_opening()

    def client_order(self, socket_handler, msg):
        self.market.orders.on_order(msg)

    def client_review(self, socket_handler, msg):
        pubkey = msg['pubkey'].decode('hex')
        text = msg['text']
        rating = msg['rating']
        self.market.reputation.create_review(pubkey, text, rating)

    # Search for markets ATM
    # TODO: multi-faceted search support
    def client_search(self, socket_handler, msg):

        self.log.info("[Search] %s", msg)
        self.transport.dht.iterative_find_value(
            msg['key'], callback=self.on_node_search_value
        )

    def client_query_network_products(self, socket_handler, msg):

        self.log.info("Querying for Contracts %s", msg)

        self.transport.dht.find_listings_by_keyword(
            msg['key'].upper(),
            callback=self.on_find_products
        )

    def client_query_store_products(self, socket_handler, msg):
        self.log.info("Searching network for contracts")

        self.transport.dht.find_listings(
            msg['key'],
            callback=self.on_find_products_by_store
        )

    def client_create_backup(self, socket_handler, msg):
        """Currently hard-coded for testing: need to find out Installation path.
        Talk to team about right location for backup files
        they might have to be somewhere outside the installation path
        as some OSes might not allow the modification of the installation
        folder
        e.g. MacOS won't allow for changes if the .app has been signed.
        and all files created by the app, have to be outside, usually at
        ~/Library/Application Support/OpenBazaar/backups ??
        """
        def on_backup_done(backup_path):
            self.log.info('Backup successfully created at %s', backup_path)
            self.send_to_client(None,
                                {
                                    'type': 'create_backup_result',
                                    'result': 'success',
                                    'detail': backup_path,
                                    'v': constants.VERSION
                                })

        def on_backup_error(error):
            self.log.info('Backup error: %s', error.strerror)
            self.send_to_client(None,
                                {'type': 'create_backup_result',
                                 'result': 'failure',
                                 'detail': error.strerror,
                                 'v': constants.VERSION})

        BackupTool.backup(BackupTool.get_installation_path(),
                          BackupTool.get_backup_path(),
                          on_backup_done,
                          on_backup_error)

    def get_backups(self, socket_handler, msg=None):
        if "127.0.0.1" == socket_handler.request.remote_ip:
            try:
                backups = [json.dumps(x, cls=BackupJSONEncoder)
                           for x in
                           Backup.get_backups(BackupTool.get_backup_path())]
                self.send_to_client(None, {'type': 'on_get_backups_response',
                                           'result': 'success',
                                           'backups': backups,
                                           'v': constants.VERSION})
            except Exception:
                self.send_to_client(None, {'type': 'on_get_backups_response',
                                           'result': 'failure',
                                           'v': constants.VERSION})

    def on_find_products_by_store(self, results):
        """Results should come in as a dictionary like:
        { u'listings': [{
            u'guid': u'18b3a8bc360fa4dd3350559c4f278fb183375d16',
            u'key': u'381ee35104d10f6249d225114f38152685d43798'
        }]}"""

        # TODO: Needs investigation but don't think this is currently used
        self.log.debug('Found Contracts: %s', type(results))
        self.log.debug(results)

        # if not isinstance(results, dict):
        #     self.log.error('Legacy node returned list of close nodes.')
        #     return

        if results.get('data') and isinstance(results['data'], unicode):
            results = json.loads(results[0])

        if 'type' not in results:
            return
        else:
            self.log.debug('Results: %s', results['contracts'])

        if results and 'data' in results:

            data = results['data']
            contracts = data['contracts']
            signature = results['signature']
            self.log.info('Signature: %s', signature)

            # Go get listing metadata and then send it to the GUI
            for contract in contracts:
                self.transport.dht.iterative_find_value(
                    contract,
                    callback=lambda msg, key=contract: (
                        self.on_node_search_value(msg, key)
                    )
                )

    def on_find_products(self, results):

        self.log.info('Found Contracts: %s', type(results))
        self.log.info(results)

        if results:
            if 'listings' in results:
                # TODO: Validate signature of listings matches data

                # Go get listing metadata and then send it to the GUI
                for contract in results['listings']:
                    self.log.debug('Results contract %s', contract)
                    key = contract.get('key', contract)

                    self.transport.send(
                        {
                            'type': 'query_listing',
                            'v': constants.VERSION,
                            'listing_id': key,
                            'senderGUID': self.transport.guid
                        },
                        contract.get('guid')
                    )

                    # TODO: Find listings on DHT when they're published there
                    # self.transport.dht.iterative_find_value(
                    #     key,
                    #     callback=lambda msg, key=key: (
                    #         self.on_global_search_value(msg, key)
                    #     )
                    # )

    def client_shout(self, socket_handler, msg):
        #msg['uri'] = self.transport.uri
        msg['pubkey'] = self.transport.pubkey
        msg['senderGUID'] = self.transport.guid
        msg['senderNick'] = self.transport.nickname
        msg['avatar_url'] = self.transport.avatar_url
        self.transport.send(protocol.shout(msg))

    def on_node_search_value(self, results, key):

        self.log.debug('Listing Data: %s %s', results, key)

        # Import gpg pubkey
        gpg = gnupg.GPG()

        # Retrieve JSON from the contract
        # 1) Remove PGP Header
        contract_data = ''.join(results.split('\n')[3:])
        index_of_signature = contract_data.find(
            '-----BEGIN PGP SIGNATURE-----', 0, len(contract_data)
        )
        contract_data_json = contract_data[0:index_of_signature]

        try:
            contract_data_json = json.loads(contract_data_json)
            seller = contract_data_json.get('Seller')
            seller_pubkey = seller.get('seller_PGP')

            gpg.import_keys(seller_pubkey)

            if gpg.verify(results):
                self.send_to_client(None, {
                    "type": "new_listing",
                    "data": contract_data_json,
                    "key": key,
                    "rawContract": results
                })
            else:

                self.log.error('Could not verify signature of contract.')

        except Exception:
            self.log.debug('Error getting JSON contract')

    def on_global_search_value(self, results, key):

        self.log.info('global search: %s %s', results, key)
        if results and not isinstance(results, list):
            self.log.debug('Listing Data: %s %s', results, key)

            # Import gpg pubkey
            gpg = gnupg.GPG()

            # Retrieve JSON from the contract
            # 1) Remove PGP Header
            contract_data = ''.join(results.split('\n')[3:])
            index_of_signature = contract_data.find(
                '-----BEGIN PGP SIGNATURE-----', 0, len(contract_data)
            )
            contract_data_json = contract_data[0:index_of_signature]

            try:
                contract_data_json = json.loads(contract_data_json)
                seller_pubkey = contract_data_json.get(
                    'Seller'
                ).get(
                    'seller_PGP'
                )

                gpg.import_keys(seller_pubkey)

                if gpg.verify(results):

                    seller = contract_data_json.get('Seller')
                    contract_guid = seller.get('seller_GUID')

                    if contract_guid == self.transport.guid:
                        nickname = self.transport.nickname
                    else:
                        routing_table = self.transport.dht.routing_table
                        peer = routing_table.get_contact(contract_guid)
                        nickname = peer.nickname if peer is not None else ""

                    self.send_to_client(None, {
                        "type": "global_search_result",
                        "data": contract_data_json,
                        "key": key,
                        "rawContract": results,
                        "nickname": nickname
                    })
                else:
                    self.log.error('Could not verify signature of contract.')

            except Exception:
                self.log.debug('Error getting JSON contract')
        else:
            self.log.info('No results')

    def on_node_search_results(self, results):
        if len(results) > 1:
            self.send_to_client(None, {
                "type": "peers",
                "peers": self.get_peers()
            })
        else:
            # Add peer to list of markets
            self.on_peer(results[0])

            # Load page for the store
            self.market.query_page(results[0].guid)

    def validate_on_peer(self, *data):
        self.log.debug('Validating on node peer message.')
        return "address" in data

    # messages coming from "the market"
    def on_peer(self, peer):
        self.log.info("Add peer: %s", peer)

        response = {'type': 'peer',
                    'pubkey': peer.pub if peer.pub else 'unknown',
                    'guid': peer.guid if peer.guid else '',
                    'uri': peer.address,
                    'v': constants.VERSION}

        self.send_to_client(None, response)

    def validate_on_peer_remove(self, *data):
        self.log.debug('Validating on node remove peer message.')
        return True

    def on_peer_remove(self, msg):
        self.send_to_client(None, msg)

    def validate_on_node_page(self, *data):
        self.log.debug('Validating on node page message.')
        return True

    def on_node_page(self, page):
        self.send_to_client(None, page)

    def validate_on_all(self, *data):
        self.log.debug('Validating on node message.')
        return True

    def on_all(self, *args):
        first = args[0]
        if isinstance(first, dict):
            self.send_to_client(None, first)
            peer = self.transport.dht.routing_table.get_contact(first.get('senderGUID'))
            if peer:
                peer.reachable = True
        else:
            self.log.info("can't format")

    # send a message
    def send_to_client(self, error, result):
        assert error is None or isinstance(error, str)
        response = {
            "id": random.randint(0, 1000000),
            "result": result
        }
        self.log.datadump('Sending to web client: %s', result)
        if error:
            response["error"] = error
        self.handler.queue_response(response)

    def send_ok(self):
        self.send_to_client(None, {"type": "ok"})

    # handler a request
    def handle_request(self, socket_handler, request):
        command = request["command"]
        self.log.info('(I) ws.ProtocolHandler.handle_request of: %s', command)
        if command not in self._handlers:
            return False
        params = request["params"]
        # Create callback handler to write response to the socket.
        self.log.debugv('found a handler!')
        self._handlers[command](socket_handler, params)
        return True

    def get_peers(self):
        peers = []
        reachable_count = 0

        for peer in self.transport.dht.active_peers:

            if peer.last_reached < time.time()-30:
                peer.reachable = False
            else:
                peer.reachable = True
                reachable_count += 1

            if hasattr(peer, 'hostname') and peer.guid[:4] != 'seed':
                peer_item = {
                    'hostname': peer.hostname,
                    'port': peer.port
                }
                if peer.pub:
                    peer_item['pubkey'] = peer.pub
                else:
                    peer_item['pubkey'] = 'unknown'

                peer_item['guid'] = peer.guid
                if peer.guid and peer.guid[:4] != 'seed':
                    peer_item['sin'] = obelisk.EncodeBase58Check(
                        '\x0F\x02%s' + peer.guid.decode('hex')
                    )
                peer_item['nick'] = peer.nickname
                peer_item['reachable'] = peer.reachable
                peer_item['avatar_url'] = peer.avatar_url
                peer_item['last_seen'] = int(time.time()-peer.last_reached)

                # self.log.debug('Peer: %s', peer)
                peers.append(peer_item)

        if reachable_count == 0:
            self.transport.join_network()

        return peers


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    # Set of WebsocketHandler
    listeners = set()

    # Protects listeners
    listen_lock = threading.Lock()

    loop = None
    log = None
    transport = None
    app_handler = None

    def initialize(self):
        # pylint: disable=arguments-differ
        # FIXME: Arguments shouldn't differ.
        self.loop = tornado.ioloop.IOLoop.instance()
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.info("Initialize WebsocketHandler")
        self.market = self.application.market
        self.transport = self.application.transport

        self.app_handler = ProtocolHandler(self)

    def open(self):
        self.log.info('Websocket open')
        self.app_handler.send_opening()
        with WebSocketHandler.listen_lock:
            self.listeners.add(self)
        self.connected = True
        # self.connected not used for any logic, might remove if unnecessary

    def on_close(self):
        self.log.info("Websocket closed")
        disconnect_msg = {
            'command': 'disconnect_client',
            'id': 0,
            'params': []
        }
        self.connected = False
        self.app_handler.handle_request(self, disconnect_msg)
        with WebSocketHandler.listen_lock:
            try:
                self.listeners.remove(self)
            except Exception:
                self.log.error('Cannot remove socket listener')

    @staticmethod
    def _check_request(request):
        return "command" in request and "id" in request and \
               "params" in request and isinstance(request["params"], dict)

    def on_message(self, message):
        self.log.datadump('Received message: %s', message)
        try:
            request = json.loads(message)
        except Exception:
            logging.error("Error decoding message: %s", message, exc_info=True)

        # Check request is correctly formed.
        if not self._check_request(request):
            logging.error("Malformed request: %s", request, exc_info=True)
            return
        if self.app_handler.handle_request(self, request):
            return

    def _send_response(self, response):
        if self.ws_connection:
            self.write_message(json.dumps(response))

    def queue_response(self, response):
        def send_response(*args):
            self._send_response(response)

        try:
            # calling write_message or the socket is not thread safe
            self.loop.current().add_callback(send_response)
        except Exception:
            logging.error("Error adding callback", exc_info=True)

    # overwrite tornado.websocket.WebSocketHandler's check_origin
    # https://github.com/tornadoweb/tornado/blob/master/tornado/websocket.py#L311
    def check_origin(self, origin):
        return True

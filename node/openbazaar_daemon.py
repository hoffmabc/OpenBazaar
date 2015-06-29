import logging
import json
import multiprocessing
import os
import signal
from threading import Lock
import time

import tornado.httpserver
import tornado.netutil
import tornado.web
from threading import Thread
from twisted.internet import reactor

from node import upnp
from node.db_store import Obdb
from node.market import Market
from node.transport import CryptoTransportLayer
from node.util import open_default_webbrowser, is_mac
from node.ws import WebSocketHandler
from node.rest import \
    RESTUsers, RESTCases, RESTSettings, RESTUsersListings, \
    RESTSalesProtest, RESTSalesRefund, RESTCasesPayMerchant, \
    RESTCasesRefundBuyer, RESTSettingsBlocked, RESTSettingsCommunication, \
    RESTSettingsKeys, RESTSales, RESTCasesSplitPayment, RESTPurchases, \
    RESTPurchasesCancel, RESTPurchasesProtest, RESTMessages, \
    RESTSearchListings, RESTSearchModerators, RESTSearchUsers, \
    RESTSearchVendors, RESTListings, RESTListingsImport
from node import constants


if is_mac():
    from node.util import osx_check_dyld_library_path

    osx_check_dyld_library_path()


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.redirect("/html/index.html")


class OpenBazaarStaticHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("X-Frame-Options", "DENY")
        self.set_header("X-Content-Type-Options", "nosniff")


class OpenBazaarContext(object):
    """
    This Object holds all of the runtime parameters
    necessary to start an OpenBazaar instance.

    This object is convenient to pass on method interfaces,
    and reduces issues of API inconsistencies (as in the order
    in which parameters are passed, which can cause bugs)
    """

    def __init__(self,
                 nat_status,
                 server_ip,
                 server_port,
                 http_ip,
                 http_port,
                 db_path,
                 log_path,
                 log_level,
                 market_id,
                 bm_user,
                 bm_pass,
                 bm_port,
                 mediator_port,
                 mediator,
                 seeds,
                 seed_mode,
                 dev_mode,
                 dev_nodes,
                 disable_upnp,
                 disable_stun_check,
                 disable_open_browser,
                 disable_sqlite_crypt,
                 enable_ip_checker):
        self.nat_status = nat_status
        self.server_ip = server_ip
        self.server_port = server_port
        self.http_ip = http_ip
        self.http_port = http_port
        self.db_path = db_path
        self.log_path = log_path
        self.log_level = log_level
        self.market_id = market_id
        self.bm_user = bm_user
        self.bm_pass = bm_pass
        self.bm_port = bm_port
        self.mediator_port = mediator_port
        self.mediator = mediator
        self.seeds = seeds
        self.seed_mode = seed_mode
        self.dev_mode = dev_mode
        self.dev_nodes = dev_nodes
        self.disable_upnp = disable_upnp
        self.disable_stun_check = disable_stun_check
        self.disable_open_browser = disable_open_browser
        self.disable_sqlite_crypt = disable_sqlite_crypt
        self.enable_ip_checker = enable_ip_checker

        # to deduce up-time, and (TODO) average up-time
        # time stamp in (non-local) Coordinated Universal Time format.
        self.started_utc_timestamp = int(time.time())

    def __repr__(self):
        representation = {"server_ip": self.server_ip,
                          "server_port": self.server_port,
                          "http_ip": self.http_ip,
                          "http_port": self.http_port,
                          "log_path": self.log_path,
                          "market_id": self.market_id,
                          "bm_user": self.bm_user,
                          "bm_pass": self.bm_pass,
                          "bm_port": self.bm_port,
                          "mediator_port": self.mediator_port,
                          "mediator": self.mediator,
                          "seeds": self.seeds,
                          "seed_mode": self.seed_mode,
                          "dev_mode": self.dev_mode,
                          "dev_nodes": self.dev_nodes,
                          "log_level": self.log_level,
                          "db_path": self.db_path,
                          "disable_upnp": self.disable_upnp,
                          "disable_open_browser": self.disable_open_browser,
                          "disable_sqlite_crypt": self.disable_sqlite_crypt,
                          "enable_ip_checker": self.enable_ip_checker,
                          "started_utc_timestamp": self.started_utc_timestamp,
                          "uptime_in_secs": (int(time.time()) -
                                             int(self.started_utc_timestamp))}

        return json.dumps(representation).replace(", ", ",\n  ")

    @staticmethod
    def get_defaults():
        return {'market_id': 1,
                'server_ip': '127.0.0.1',
                'server_port': 12345,
                'log_dir': 'logs',
                'log_file': 'production.log',
                'dev_log_file': 'development-{0}.log',
                'db_dir': 'db',
                'db_file': 'ob.db',
                'dev_db_file': 'ob-dev-{0}.db',
                'dev_mode': False,
                'dev_nodes': 3,
                'seed_mode': False,
                'seeds': [
                    ('205.186.154.163', 12345),
                    ('205.186.156.31', 12345)
                    # ('seed.openlabs.co', 12345),
                    #('us.seed.bizarre.company', 12345),
                    #('eu.seed.bizarre.company', 12345)
                ],
                'disable_upnp': False,
                'disable_stun_check': False,
                'disable_open_browser': False,
                'disable_sqlite_crypt': False,
                'log_level': 30,
                # CRITICAL=50 ERROR=40 WARNING=30 DEBUG=10 DEBUGV=9 DATADUMP=5 NOTSET=0
                'http_ip': '127.0.0.1',
                'http_port': 0,
                'bm_user': None,
                'bm_pass': None,
                'bm_port': -1,
                'mediator_port': 5000,
                'mediator': False,
                'enable_ip_checker': False,
                'config_file': None}

    @staticmethod
    def create_default_instance():
        defaults = OpenBazaarContext.get_defaults()
        return OpenBazaarContext(
            None,
            server_ip=defaults['server_ip'],
            server_port=defaults['server_port'],
            http_ip=defaults['http_ip'],
            http_port=defaults['http_port'],
            db_path=os.path.join(defaults['db_dir'], defaults['db_file']),
            log_path=os.path.join(defaults['log_dir'], defaults['log_file']),
            log_level=defaults['log_level'],
            market_id=defaults['market_id'],
            bm_user=defaults['bm_user'],
            bm_pass=defaults['bm_pass'],
            bm_port=defaults['bm_port'],
            mediator_port=defaults['mediator_port'],
            mediator=defaults['mediator'],
            seeds=defaults['seeds'],
            seed_mode=defaults['seed_mode'],
            dev_mode=defaults['dev_mode'],
            dev_nodes=defaults['dev_nodes'],
            disable_upnp=defaults['disable_upnp'],
            disable_stun_check=defaults['disable_stun_check'],
            disable_open_browser=defaults['disable_open_browser'],
            disable_sqlite_crypt=defaults['disable_sqlite_crypt'],
            enable_ip_checker=defaults['enable_ip_checker']
        )


class MarketApplication(tornado.web.Application):
    def __init__(self, ob_ctx):
        self.shutdown_mutex = Lock()
        self.ob_ctx = ob_ctx
        self.loop = tornado.ioloop.IOLoop.instance()
        db_connection = Obdb(ob_ctx.db_path, ob_ctx.disable_sqlite_crypt)
        self.db = db_connection
        self.transport = CryptoTransportLayer(ob_ctx, db_connection)
        self.market = Market(self.transport, db_connection)
        self.upnp_mapper = None

        Thread(target=reactor.run, args=(False,)).start()

        # Mediator is used to route messages between NAT'd peers
        # self.mediator = Mediator(self.ob_ctx.http_ip, self.ob_ctx.mediator_port)

        peers = ob_ctx.seeds if not ob_ctx.seed_mode else []
        self.transport.join_network(peers)

        handlers = [
            (r"/", MainHandler),
            (r"/main", MainHandler),
            (r"/html/(.*)", OpenBazaarStaticHandler, {'path': './html'}),
            (r"/ws", WebSocketHandler),
            (r"/api/users/?(.*)", RESTUsers),
            (r"/api/users/(.*)/listings", RESTUsersListings),
            (r"/api/users/(.*)/listings/?(.*)", RESTUsersListings),
            (r"/api/users/(.*)/follow", RESTUsersListings),
            (r"/api/users/(.*)/unfollow", RESTUsersListings),
            (r"/api/users/(.*)/reputation", RESTUsersListings),
            (r"/api/cases/?(.*)", RESTCases),
            (r"/api/cases/(.*)/refund_buyer", RESTCasesRefundBuyer),
            (r"/api/cases/(.*)/pay_merchant", RESTCasesPayMerchant),
            (r"/api/cases/(.*)/split_payment", RESTCasesSplitPayment),
            (r"/api/sales/?(.*)", RESTSales),
            (r"/api/sales/(.*)/refund", RESTSalesRefund),
            (r"/api/sales/(.*)/protest", RESTSalesProtest),
            (r"/api/purchases/?(.*)", RESTPurchases),
            (r"/api/purchases/(.*)/cancel", RESTPurchasesCancel),
            (r"/api/purchases/(.*)/protest", RESTPurchasesProtest),
            (r"/api/settings/?(.*)", RESTSettings),
            (r"/api/settings/keys", RESTSettingsKeys),
            (r"/api/settings/communication", RESTSettingsCommunication),
            (r"/api/settings/blocked", RESTSettingsBlocked),
            (r"/api/messages/?(.*)", RESTMessages),
            (r"/api/search/vendors/(.*)", RESTSearchVendors),
            (r"/api/search/moderators/(.*)", RESTSearchModerators),
            (r"/api/search/listings/(.*)", RESTSearchListings),
            (r"/api/search/users/(.*)", RESTSearchUsers),
            (r"/api/listings/?(.*)", RESTListings),
            (r"/api/listings/import", RESTListingsImport)
        ]

        # TODO: Move debug settings to configuration location
        settings = dict(debug=True)
        super(MarketApplication, self).__init__(handlers, **settings)

    def start_app(self):
        # If self.ob_ctx.http_port is 0, the kernel is queried for a port.
        sockets = tornado.netutil.bind_sockets(
            self.ob_ctx.http_port,
            address=self.ob_ctx.http_ip
        )
        server = tornado.httpserver.HTTPServer(self)
        server.add_sockets(sockets)

        self.ob_ctx.http_port = sockets[0].getsockname()[1]

        if not self.ob_ctx.disable_upnp:
            self.setup_upnp_port_mappings(self.ob_ctx.server_port)
        else:
            print "MarketApplication.start_app(): Disabling upnp setup"

    def setup_upnp_port_mappings(self, p2p_port):
        result = False

        if not self.ob_ctx.disable_upnp:
            upnp.PortMapper.DEBUG = False
            print "Setting up UPnP Port Map Entry..."
            self.upnp_mapper = upnp.PortMapper()
            self.upnp_mapper.clean_my_mappings(p2p_port)

            result_tcp_p2p_mapping = self.upnp_mapper.add_port_mapping(
                p2p_port, p2p_port
            )
            print "UPnP TCP P2P Port Map configuration done ",
            print "(%s -> %s) => %s" % (
                p2p_port, p2p_port, result_tcp_p2p_mapping
            )

            result_udp_p2p_mapping = self.upnp_mapper.add_port_mapping(
                p2p_port, p2p_port, 'UDP'
            )
            print "UPnP UDP P2P Port Map configuration done ",
            print "(%s -> %s) => %s" % (
                p2p_port, p2p_port, result_udp_p2p_mapping
            )

            result = result_tcp_p2p_mapping and result_udp_p2p_mapping
            if not result:
                print "Warning: UPnP was not setup correctly. ",
                print "Ports could not be automatically mapped."
                print "If you only see two or three stores, here are some tips:"
                print "1. If you are using VPN, configure port forwarding or disable your VPN temporarily"
                print "2. Configure your router to forward traffic from port",
                print "%s for both TCP and UDP to your local port %s" % (p2p_port, p2p_port)

        return result

    def cleanup_upnp_port_mapping(self):
        if not self.ob_ctx.disable_upnp:
            try:
                if self.upnp_mapper is not None:
                    print "Cleaning UPnP Port Mapping -> ", \
                        self.upnp_mapper.clean_my_mappings(self.transport.port)
            except AttributeError:
                print (
                    "[openbazaar] "
                    "MarketApplication.clean_upnp_port_mapping() failed!"
                )

    def shutdown(self, x_param=None, y_param=None):
        self.shutdown_mutex.acquire()
        print "MarketApplication.shutdown!"
        log = logging.getLogger(
            '[%s] %s' % (self.market.market_id, 'root')
        )
        log.info("Received TERMINATE, exiting...")

        # Send goodbye message to connected peers
        for peer in self.transport.dht.active_peers:
            peer.send_raw(
                json.dumps({
                    'type': 'goodbye',
                    'pubkey': self.transport.pubkey,
                    'senderGUID': self.transport.guid,
                    'hostname': self.transport.hostname,
                    'port': self.transport.port,
                    'senderNick': self.transport.nickname,
                    'avatar_url': self.transport.avatar_url,
                    'v': constants.VERSION
                })
            )

        self.cleanup_upnp_port_mapping()
        self.loop.stop()

        self.transport.shutdown()
        self.shutdown_mutex.release()
        os._exit(0)


def start_io_loop():
    if not tornado.ioloop.IOLoop.instance():
        tornado.ioloop.install()

    try:
        tornado.ioloop.IOLoop.instance().start()
    except Exception as exc:
        print "openbazaar::start_io_loop Exception:", exc
        raise


def create_logger(ob_ctx):
    logger = None
    try:
        logger = logging.getLogger()
        logger.setLevel(int(ob_ctx.log_level))

        handler = logging.handlers.RotatingFileHandler(
            ob_ctx.log_path,
            encoding='utf-8',
            maxBytes=50000000,
            backupCount=1
        )
        log_format = logging.Formatter(
            u'%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(log_format)
        logger.addHandler(handler)

    except Exception as exc:
        print "Could not setup logger, continuing: ", exc.message
    return logger


def log_openbazaar_start(log, ob_ctx):
    log.info("Started OpenBazaar Web App at http://%s:%s" %
             (ob_ctx.http_ip, ob_ctx.http_port))
    print "Started OpenBazaar Web App at http://%s:%s" % (ob_ctx.http_ip, ob_ctx.http_port)


def attempt_browser_open(ob_ctx):
    if not ob_ctx.disable_open_browser:
        open_default_webbrowser(
            'http://%s:%s' % (ob_ctx.http_ip, ob_ctx.http_port))


def setup_signal_handlers(application):
    try:
        signal.signal(signal.SIGTERM, application.shutdown)
        signal.signal(signal.SIGINT, application.shutdown)
    except ValueError:
        pass


def node_starter(ob_ctxs):
    # This is the target for the the Process which
    # will spawn the children processes that spawn
    # the actual OpenBazaar instances.

    for ob_ctx in ob_ctxs:
        process = multiprocessing.Process(
            target=start_node, args=(ob_ctx,),
            name="Process::openbazaar_daemon::target(start_node)")
        process.daemon = False  # python has to wait for this user thread to end.
        process.start()
        time.sleep(1)


def start_node(ob_ctx):
    logger = create_logger(ob_ctx)
    application = MarketApplication(ob_ctx)
    setup_signal_handlers(application)
    application.start_app()
    log_openbazaar_start(logger, ob_ctx)
    attempt_browser_open(ob_ctx)
    start_io_loop()

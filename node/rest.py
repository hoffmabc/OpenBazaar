# import threading
import logging
# import subprocess
# import pycountry
# import gnupg
# import obelisk
# import json
# import random
# import time
# import urllib2
# from bitcoin import (
#     apply_multisignatures,
#     mk_multisig_script,
#     mktx,
#     multisign,
#     scriptaddr
# )
# from tornado import iostream
import tornado.web
# from twisted.internet import reactor
# from node import constants, protocol, trust
# from node.backuptool import BackupTool, Backup, BackupJSONEncoder
# import bitcoin


class RESTHandler(tornado.web.RequestHandler):
    loop = None
    log = None
    market_application = None
    market = None
    transport = None
    app_handler = None

    def initialize(self):
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.info("Initialize RESTHandler")

        self.loop = self.application.loop
        self.market_application = self.application
        self.market = self.market_application.market
        self.transport = self.application.transport


class RESTUsers(RESTHandler):
    def get(self, GUID):
        assert (GUID, 'You must send a GUID')

        self.write('GUID: %s' % GUID)


class RESTUsersListings(RESTHandler):
    def get(self, guid):
        self.write({'listings': ''})


class RESTMessages(RESTHandler):
    def get(self):
        self.write({})


class RESTSearchVendors(RESTHandler):
    def get(self):
        self.write({})


class RESTSearchUsers(RESTHandler):
    def get(self):
        self.write({})


class RESTSearchListings(RESTHandler):
    def get(self):
        self.write({})


class RESTSearchModerators(RESTHandler):
    def get(self):
        self.write({})


class RESTCases(RESTHandler):
    def get(self):
        self.write({})


class RESTCasesRefundBuyer(RESTHandler):
    def get(self):
        self.write({})


class RESTCasesPayMerchant(RESTHandler):
    def get(self):
        self.write({})


class RESTCasesSplitPayment(RESTHandler):
    def get(self):
        self.write({})


class RESTPurchases(RESTHandler):
    def get(self, purchase_id=None):
        if purchase_id:
            self.write({
                'purchase_id': purchase_id
            })
        else:
            self.write({})


class RESTPurchasesCancel(RESTHandler):
    def get(self, purchase_id):
        self.write({})


class RESTPurchasesProtest(RESTHandler):
    def get(self, purchase_id):
        self.write({})


class RESTSettings(RESTHandler):
    def get(self):
        self.write({})


class RESTSettingsKeys(RESTHandler):
    def get(self):
        self.write({})


class RESTSettingsCommunication(RESTHandler):
    def get(self):
        self.write({})


class RESTSettingsBlocked(RESTHandler):
    def get(self):
        self.write({})


class RESTSales(RESTHandler):
    def get(self):
        self.write({})


class RESTSalesProtest(RESTHandler):
    def get(self):
        self.write({})


class RESTSalesRefund(RESTHandler):
    def get(self):
        self.write({})


class RESTListings(RESTHandler):
    def get(self):
        self.write({})


class RESTListingsImport(RESTHandler):
    def get(self):
        self.write({})
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
    def get(self):
        """Return User object with the specified GUID
        """
        self.log.info('[REST/GET] /users')

        # Get URL Params
        guid = self.get_argument('user_id')

        # Validate
        assert(len(guid) > 0, 'There is no GUID specified.')

        # Pass off to the underlying module
        self.write('GUID: %s' % guid)


class RESTUsersFollow(RESTHandler):
    def post(self):
        """Add User designated by specified GUID as someone
        to follow
        """
        self.log.info('[REST/POST] /users/follow')

        guid = self.get_argument('user_id')

        assert(len(guid) > 0, 'No GUID is specified')

        # users.follow_user(guid)


class RESTUsersUnfollow(RESTHandler):
    def post(self):
        """Remove User designated by specified GUID from a
        follow list
        """
        self.log.info('[REST/POST] /users/unfollow')

        guid = self.get_argument('user_id')

        assert(len(guid) > 0, 'No GUID is specified')

        # users.unfollow_user(guid)


class RESTUsersReputation(RESTHandler):
    def post(self):
        """Retrieve a reputation score for a user from
        the network.
        """
        self.log.info('[REST/GET] /users/reputation')

        guid = self.get_argument('user_id')

        assert(len(guid) > 0, 'No GUID is specified')

        # users.reputation(guid)


class RESTUsersListings(RESTHandler):
    def get(self):
        """Get Listings from a user specified by the GUID
        """
        self.log.info('[REST/GET] /users/listings')

        guid = self.get_argument('user_id')
        count = self.get_argument('count')
        offset = self.get_argument('offset')

        assert(len(guid) > 0, 'No GUID is specified')

        # users.listings(guid, count, offset)


class RESTMessages(RESTHandler):
    def get(self):
        """Retrieve messages from private inbox.
        """
        self.log.info('[REST/GET] /messages')

        count = self.get_argument('count')
        offset = self.get_argument('offset')
        from_user = self.get_argument('from_user')
        to_user = self.get_argument('offset')

        # inbox.messages(count, offset, from_user, to_user)


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
        """Retrieving moderator cases the current user is
        participating in.
        """
        self.log.info('[REST/GET] /cases')

        count = self.get_argument('count')
        offset = self.get_argument('offset')

        # market.get_cases(count, offset)


class RESTCasesRefundBuyer(RESTHandler):
    def post(self):
        """Refund payment to a buyer for a specific case.
        """
        self.log.info('[REST/POST] /cases/refund_buyer')

        case_id = self.get_argument('case_id')

        assert(len(case_id) > 0, 'No Case ID is specified')

        # cases.refund_buyer(case_id)


class RESTCasesPayVendor(RESTHandler):
    def post(self):
        """Release payment to vendor for a specific case.
        """
        self.log.info('[REST/POST] /cases/pay_vendor')

        case_id = self.get_argument('case_id')

        assert(len(case_id) > 0, 'No Case ID is specified')

        # cases.pay_vendor(case_id)


class RESTCasesSplitPayment(RESTHandler):
    def post(self):
        """Allows moderator to split escrow across both parties
        for a specific case.
        """
        self.log.info('[REST/POST] /cases/split_payment')

        case_id = self.get_argument('case_id')
        amount_to_buyer = self.get_argument('amount_to_buyer')

        assert(len(case_id) > 0, 'No Case ID is specified')
        assert(0 >= amount_to_buyer > 100, 'Invalid %')

        # cases.split_payment(case_id, amount_to_buyer)


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
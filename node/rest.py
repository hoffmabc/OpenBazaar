import logging
import tornado.web


class RESTHandler(tornado.web.RequestHandler):
    loop = None
    log = None
    market_application = None
    market = None
    transport = None
    app_handler = None

    def initialize(self):
        self.log = logging.getLogger(self.__class__.__name__)
        self.log.debug("Initialize RESTHandler")

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
        assert len(guid) > 0, 'There is no GUID specified.'

        # Pass off to the underlying module
        self.write('GUID: %s' % guid)


class RESTUsersListings(RESTHandler):
    def get(self):
        """Retrieving contract listings for a specific user
        on the network.
        """
        self.log.info('[REST/GET] /users/listings')

        guid = self.get_argument('user_id')
        count = self.get_argument('count')
        offset = self.get_argument('offset')

        # Validate
        assert len(guid) > 0, 'There is no GUID specified.'

        # market.listings_by_user_id(guid, count, offset)


class RESTUsersFollow(RESTHandler):
    def post(self):
        """Add User designated by specified GUID as someone
        to follow
        """
        self.log.info('[REST/POST] /users/follow')

        guid = self.get_argument('user_id')

        assert len(guid) > 0, 'No GUID is specified'

        # users.follow_user(guid)


class RESTUsersUnfollow(RESTHandler):
    def post(self):
        """Remove User designated by specified GUID from a
        follow list
        """
        self.log.info('[REST/POST] /users/unfollow')

        guid = self.get_argument('user_id')

        assert len(guid) > 0, 'No GUID is specified'

        # users.unfollow_user(guid)


class RESTUsersReputation(RESTHandler):
    def post(self):
        """Retrieve a reputation score for a user from
        the network.
        """
        self.log.info('[REST/GET] /users/reputation')

        guid = self.get_argument('user_id')

        assert len(guid) > 0, 'No GUID is specified'

        # users.reputation(guid)


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


class RESTMessagesSend(RESTHandler):
    def post(self):
        """Send a new private message to another user.
        """
        self.log.info('[REST/POST] /messages/send')

        recipient_id = self.get_argument('recipient_id')
        body = self.get_argument('body')

        assert len(recipient_id) > 0, 'No GUID is specified'
        assert len(body) > 0, 'Empty message'

        # inbox.send_message(recipient_id, body)


class RESTMessagesClearConversation(RESTHandler):
    def post(self):
        """Mark all current messages with a user as hidden.
        """
        self.log.info('[REST/POST] /messages/clear_conversation')

        user_id = self.get_argument('user_id')

        assert len(user_id) > 0, 'No GUID is specified'

        # inbox.clear_conversation(user_id)


class RESTSearch(RESTHandler):
    def get(self):
        """Search for anything on the network.
        """
        self.log.info('[REST/GET] /search')

        count = self.get_argument('count')
        query = self.get_argument('query')

        assert len(query) > 0, 'No search query provided'

        # search.find(query, count)


class RESTSearchVendors(RESTHandler):
    def get(self):
        """Search for vendor users.
        """
        self.log.info('[REST/GET] /search/vendors')

        count = self.get_argument('count')
        query = self.get_argument('query')

        assert len(query) > 0, 'No search query provided'

        # search.find_vendors(query, count)


class RESTSearchModerators(RESTHandler):
    def get(self):
        """Search for moderator users.
        """
        self.log.info('[REST/GET] /search/moderators')

        count = self.get_argument('count')
        query = self.get_argument('query')

        assert len(query) > 0, 'No search query provided'

        # search.find_moderators(query, count)


class RESTSearchListings(RESTHandler):
    def get(self):
        """Search for market listings.
        """
        self.log.info('[REST/GET] /search/listings')

        count = self.get_argument('count')
        query = self.get_argument('query')

        assert len(query) > 0, 'No search query provided'

        # search.find_listings(query, count)


class RESTSearchUsers(RESTHandler):
    def get(self):
        """Search for users.
        """
        self.log.info('[REST/GET] /search/users')

        count = self.get_argument('count')
        query = self.get_argument('query')

        assert len(query) > 0, 'No search query provided'

        # search.find_users(query, count)


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

        assert len(case_id) > 0, 'No Case ID is specified'

        # cases.refund_buyer(case_id)


class RESTCasesPayVendor(RESTHandler):
    def post(self):
        """Release payment to vendor for a specific case.
        """
        self.log.info('[REST/POST] /cases/pay_vendor')

        case_id = self.get_argument('case_id')

        assert len(case_id) > 0, 'No Case ID is specified'

        # cases.pay_vendor(case_id)


class RESTCasesSplitPayment(RESTHandler):
    def post(self):
        """Allows moderator to split escrow across both parties
        for a specific case.
        """
        self.log.info('[REST/POST] /cases/split_payment')

        case_id = self.get_argument('case_id')
        amount_to_buyer = self.get_argument('amount_to_buyer')

        assert len(case_id) > 0, 'No Case ID is specified'
        assert 0 >= amount_to_buyer > 100, 'Invalid %'

        # cases.split_payment(case_id, amount_to_buyer)


class RESTPurchases(RESTHandler):
    def get(self):
        """Retrieving orders that the current user is the buyer for.
        """
        self.log.info('[REST/GET] /purchases')

        count = self.get_argument('count')
        offset = self.get_argument('offset')
        order_filter = self.get_argument('filter')

        # market.purchases(count, offset, order_filter)


class RESTPurchasesProtest(RESTHandler):
    def post(self):
        """Allows buyer to protest the order to a moderator in the
        event of a problem.
        """
        self.log.info('[REST/POST] /purchases/protest')

        order_id = self.get_argument('order_id')
        message_to_mod = self.get_argument('message_to_mod')

        assert len(order_id) > 0, 'No Order ID is specified'
        assert len(message_to_mod) > 0, 'No message content'

        # purchases.protest(order_id, message_to_mod)


class RESTPurchasesCancel(RESTHandler):
    def post(self):
        """Allows buyer to cancel in order and request a refund.
        """
        self.log.info('[REST/POST] /purchases/cancel')

        order_id = self.get_argument('order_id')
        reason = self.get_argument('reason')

        assert len(order_id) > 0, 'No Order ID is specified'

        # purchases.cancel(order_id, reason)


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
        """Retrieving orders that the current user is the vendor for.
        """
        self.log.info('[REST/GET] /sales')

        count = self.get_argument('count')
        offset = self.get_argument('offset')
        sales_filter = self.get_argument('filter')

        # market.sales(count, offset, sales_filter)


class RESTSalesProtest(RESTHandler):
    def post(self):
        """Allows vendor to protest the order to a moderator in the
        event of a problem.
        """
        self.log.info('[REST/POST] /sales/protest')

        order_id = self.get_argument('order_id')
        message_to_mod = self.get_argument('message_to_mod')

        assert len(order_id) > 0, 'No Order ID is specified'
        assert len(message_to_mod) > 0, 'No message content'

        # sales.protest(order_id, message_to_mod)


class RESTSalesRefund(RESTHandler):
    def post(self):
        """Allows vendor to refund the buyer and cancel the order.
        """
        self.log.info('[REST/POST] /sales/refund')

        order_id = self.get_argument('order_id')

        assert len(order_id) > 0, 'No Order ID is specified'

        # sales.refund(order_id)


class RESTListings(RESTHandler):
    def get(self):
        """Retrieve current user's listings.
        """
        self.log.info('[REST/GET] /listings')

        query = self.get_argument('query')
        count = self.get_argument('count')
        offset = self.get_argument('offset')

        # market.my_listings(count, offset, query)


# class RESTListingsImport(RESTHandler):
#     def get(self):
#         self.write({})

# -*- coding: utf-8 -*-
"""
    flaskext.payments
    ~~~~~~~~~~~~~~~~~

    Generic Payment gateway classes for Flask Payment
    May be dirtied with Paypal classes in the first instance

    :copyright: (c) 2010 by jgumbley.
    :license: BSD, see LICENSE for more details.
"""

from paypal import PayPalInterface, PayPalConfig

class PaymentsConfigurationError(Exception): pass
class PaymentsValidationError(Exception): pass
class PaymentsErrorFromGateway(Exception): pass

class Payments(object):
    """
    Manages payment processing

    :param app: Flask instance

    """

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initializes payment gateway from the application settings.

        You can use this if you want to set up your Payment instance
        at configuration time.

        Binds to a specific implementation class based on the value
        in the PAYMENTS_API config value. 

        :param app: Flask application instance

        """
        # initialise gateway based on configuration
        self._init_gateway(app)
       
        self.testing = app.config.get('TESTING')
        self.app = app # this Payments instance reference to the Flask app

    def _init_gateway(self, app):
        """what i'm trying to do here is have some logic to conditionally
        instantiate a "payment gateway" member depending on the configuration
        of the PAYMENT_API configuration parameter.
        
        want to fail early if gateway not properly configured, so the idea
        is to delegate to the payment gateway class at this point to give it
        to the opptunity to validate its configuration and fail if needs be.
        """
        gateways = {
            'PayPal': PayPalGateway
        }
        try:
            self.gateway = gateways[app.config.get('PAYMENT_API')](app)
        except KeyError:
            raise PaymentsConfigurationError

    def setupRedirect(self, trans):
        """Some gateways such as PayPal WPP Express Checkout and Google payments
        require you to redirect your customer to them first to collect info, 
        so going to make an explict getRedirect method for these instances.

        Returns the transaction with the redirect url attached. I guess the idea
        is the app stuffs this in the session and when it gets the user back
        will call authorise using this transaction.
        """
        if trans.validate(): # generic gateway abstract validation 
            return self.gateway.setupRedirect(trans) # gateway implementation does own
        else: raise PaymentTransactionValidationError()


    def authorise(self, trans):
        """Returns a valid authorisation (accepted or declined) or an error,
        which can be application (i.e. validation) or a system error (i.e. 500).
        
        The transaction is subject to gernic validatation, i.e. does it have
        necessary fields and do they add up, and only if valid will the
        instantiated gateway be invoked.

        """
        if trans.validate(): # generic gateway abstract validation 
            return self.gateway.authorise(trans) # gateway implementation does own
        else: raise PaymentTransactionValidationError()

class Transaction(object):
    """The payment request value object, with some validation logic
    It look like the way this is going the various gateways will be able to add
    whatever they like to this as and when they want.

    Not sure whether to subclass this and use some kind of factory so the app
    will get the right one depending on how they've instantiated Payments.
    """

    def validate(self):
        """
        validate the details of the payment, i.e. run regex on credit card
        number, ensure all required fields are filled etc.
        
        """
        return True

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.authorised = False
        pass

# ------------------------------------------------------------------------

import urllib, datetime

class PayPalGateway:
    """ Specific Impementation for PayPal WPP"""
    
    def __init__(self, app):
        # Need to catch value error and throw as config error
        try:
            self._init_API(app)
        except KeyError:
            raise PaymentsConfigurationError
            
    def _init_API(self ,app):
        """ initialises any stuff needed for the payment gateway API and should
        fail if anything is invalid or missing
        """
        config = PayPalConfig(
            API_ENVIRONMENT=app.config.get('PAYMENT_API_ENVIRONMENT', 'sandbox'),
            API_USERNAME=app.config.get('PAYPAL_API_USER'),
            API_PASSWORD=app.config.get('PAYPAL_API_PWD'),
            API_SIGNATURE=app.config.get('PAYPAL_API_SIGNATURE')
        )
        self.interface = PayPalInterface(config)

    def setupRedirect(self, trans):
        """ this is for WPP only"""
        if trans.type == 'Express':
            return self._setupExpressTransfer(trans)
        else:
            raise PaymentTransactionValidationError()

    # why is this two methods surely this could be easier?

    def _setupExpressTransfer(self, trans):
        """ add details to transaction to allow it to be forwarded to the 
        third party gateway 
        """
        def keycase(key):
            return key.replace('_','').upper()
        params = dict([(keycase(k), v,) for k, v in trans.__dict__.iteritems()])
        r = self.SetExpressCheckout(**params)
        trans.token = r.token
        trans.next = self.interface.generate_express_checkout_redirect_url(
                r.token)
        return trans

    # Public methods of gateway 'interface'
    def authorise(self, trans):
        """Examines the type of transaction passed in and delegates to either
        the express payments flow or the direct payments flow, where further
        validation can take place.

        If its not a type of transaction which this gateway can process then it
        will throw its dummy out of the pram.
        """
        if trans.type == 'Express':
            return self._authoriseExpress(trans)
        elif trans.type == 'Direct':
            pass # not implemented yet
        else: raise PaymentTransactionValidationError()

    def _authoriseExpress(self, trans, action='Sale'):
        """ calls authorise on payment setup via redirect to paypal
        """
        r = self.DoExpressCheckoutPayment(token=trans.token,
                PAYMENTACTION=action, PAYERID=trans.payerid, AMT=trans.amt,
                CURRENCYCODE='JPY')
        trans.transactionid = r.TRANSACTIONID
        trans.raw = r
        trans.authorised = True
        return trans

    # API METHODS

    # PayPal python NVP API wrapper class.
    # This is a sample to help others get started on working
    # with the PayPal NVP API in Python. 
    # This is not a complete reference! Be sure to understand
    # what this class is doing before you try it on production servers!
    # ...use at your own peril.

    ## see https://www.paypal.com/IntegrationCenter/ic_nvp.html
    ## and
    ## https://www.paypal.com/en_US/ebook/PP_NVPAPI_DeveloperGuide/index.html
    ## for more information.

    # by Mike Atlas / LowSingle.com / MassWrestling.com, September 2007
    # No License Expressed. Feel free to distribute, modify, 
    # and use in any open or closed source project without credit to the author

    def SetExpressCheckout(self, **kwargs):
        return self.interface.set_express_checkout(**kwargs)
    
    def DoExpressCheckoutPayment(self, token, **kwargs):
        return self.interface.do_express_checkout_payment(token, **kwargs)

    # Get info on transaction
    def GetTransactionDetails(self, **kwargs):
        return self.interface.get_transaction_details(**kwargs)

    # Direct payment
    def DoDirectPayment(self, **kwargs):
        return self.interface.do_direct_payment(**kwargs)


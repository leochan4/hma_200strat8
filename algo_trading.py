from ib_insync import *
import threading

'''class APIController(EWrapper): #takes in the EWrapper that communicates info from server to python

    def __init__(self):
        pass

    def connectAck(self):
        #when a successful connection is instantiated between server and python
        print('Connected')

class APISocket(EClient): #takes in the EClient that communicates info from python to server


    def __init__(self, wrapper):

        super().__init__(wrapper)

class TradingApplication(APIController, APISocket):

    def __init__(self):
        APIController.__init__(self)
        APISocket.__init__(self, wrapper=self)

        self.connect('127.0.0.1', 4002, 0)

        t = threading.Thread(self.run)

        t.start()


TradingApplication()'''
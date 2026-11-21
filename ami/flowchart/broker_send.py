import pickle

import zmq


def send_to_broker(sock, topic, msg):
    """Send ``msg`` for the node process called ``topic`` on a synchronous PUB socket.

    Both frames go out in one ``send_multipart`` call so they can not be separated.  The frames are what
    ``send_string(topic, SNDMORE)`` followed by ``send_pyobj(msg)`` produce, so the receivers
    (``recv_string`` then ``recv_pyobj``) need no change.  A PUB send does not wait for subscribers.
    """
    sock.send_multipart([topic.encode("utf-8"), pickle.dumps(msg, protocol=pickle.DEFAULT_PROTOCOL)], zmq.NOBLOCK)

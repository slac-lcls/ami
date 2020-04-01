import zmq
from ami.data import Deserializer

if __name__ == '__main__':
    ctx = zmq.Context()

    profile_comm = ctx.socket(zmq.SUB)
    profile_comm.setsockopt_string(zmq.SUBSCRIBE, '')
    profile_comm.connect("tcp://127.0.0.1:5564")
    deserializer = Deserializer()

    while True:
        topic = profile_comm.recv_string()
        node = profile_comm.recv_string()
        payload = profile_comm.recv_serialized(deserializer, copy=False)
        print(topic, node, payload)

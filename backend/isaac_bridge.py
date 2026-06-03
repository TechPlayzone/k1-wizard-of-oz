isaac_bridge = type('obj', (object,), {'start': lambda s: None, 'send_move': lambda s,c,d=2.0: None, 'send_gesture': lambda s,n: None, 'available': False})()

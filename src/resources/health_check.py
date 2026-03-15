import falcon
import json

class HealthCheckResource(object):
    def on_get(self, req, resp):
        response_json = { 
            'status': 'ok'
        }
        resp.text = json.dumps(response_json)
        resp.status = falcon.HTTP_200
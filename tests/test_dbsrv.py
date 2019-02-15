import json
import logging
import os
import unittest

import db_app

dirpath = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)


class DbSrvTest(unittest.TestCase):

    def setUp(self):
        db_app.app.testing = True
        self.app = db_app.app.test_client()
        db_app.app.servers = {
            "rouser": [
                "mysql://rouser@localhost:3306/",
                "mysql://rouser@locohost:3306/"
            ],
            "rwuser": [
                "mysql://rwuser:pwd@localhost:3306/",
                "mysql://rwuser:pwd@locohost:3306/"
            ]
        }
        db_app.app.conf['smtp_server'] = '127.0.0.1'

    def test_list_servers_single(self):
        response = self.app.get("/servers/rouser?query=loca");
        self.assertEquals(200, response.status_code)
        results = json.loads(response.data);
        self.assertEquals(1, len(results))
        self.assertTrue("mysql://rouser@localhost:3306/" in results)
        self.assertFalse("mysql://rouser@locohost:3306/" in results)

    def test_list_servers_nouser(self):
        response = self.app.get("/servers/rauser?query=loca");
        self.assertEquals(400, response.status_code)

    def test_list_servers_none(self):
        response = self.app.get("/servers/rouser?query=boca");
        self.assertEquals(200, response.status_code)
        results = json.loads(response.data);
        self.assertEquals(0, len(results))

    def test_list_servers_double(self):
        response = self.app.get("/servers/rouser?query=loc");
        self.assertEquals(200, response.status_code)
        results = json.loads(response.data);
        self.assertEquals(2, len(results))
        self.assertTrue("mysql://rouser@localhost:3306/" in results)
        self.assertTrue("mysql://rouser@locohost:3306/" in results)

    def tearDown(self):
        logging.info("Teardown")


if __name__ == '__main__':
    unittest.main()

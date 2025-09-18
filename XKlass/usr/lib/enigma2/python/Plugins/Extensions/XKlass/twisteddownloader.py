#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
from twisted.internet import reactor
from twisted.web.client import readBody
from twisted.web.http_headers import Headers

try:
    from twisted.web.client import BrowserLikePolicyForHTTPS
    contextFactory = BrowserLikePolicyForHTTPS()
except ImportError:
    from twisted.web.client import WebClientContextFactory
    contextFactory = WebClientContextFactory()


class DataDownloader:
    def __init__(self, agent, python_version):
        self.agent = agent
        self.python_version = python_version

    def downloadData(self, searchurl, filepath, callback, data_type, errback, timeout=10):
        print("*** downloadData ***")
        try:
            if self.python_version == 3:
                self.data_download_deferred = self.agent.request(
                    b'GET',
                    searchurl,
                    Headers({'User-Agent': [b"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]}),
                    None
                )
            else:
                self.data_download_deferred = self.agent.request(
                    'GET',
                    searchurl,
                    Headers({'User-Agent': ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]}),
                    None
                )

            # Adding a timeout to the deferred (this will cancel it if it exceeds the timeout)
            self.data_download_deferred = self.data_download_deferred.addTimeout(timeout, reactor)

            # Adding callbacks to process the result and handle errors
            self.data_download_deferred.addCallback(self.handleResponse, filepath, callback, data_type, errback)  # Pass errback here
            self.data_download_deferred.addErrback(errback)  # Use the passed errback function

        except Exception as e:
            print("Download error: {}".format(e))

    def handleResponse(self, response, filepath, callback, data_type, errback, redirect_count=0):
        print("*** handleResponse ***")
        if response.code == 200:
            d = readBody(response)
            d.addCallback(self.processData, filepath, callback, data_type)
            return d
        elif response.code in (301, 302):  # Handle redirects
            if redirect_count >= 2:
                print("Exceeded maximum redirects. Stopping further processing.")
                self.failed()
                return

            new_location = response.headers.getRawHeaders('location')
            if new_location:
                new_url = new_location[0].decode() if self.python_version == 3 else new_location[0]
                print("Redirecting to:", new_url)
                return self.downloadData(new_url, filepath, callback, data_type, errback, redirect_count + 1)  # Pass errback here
            else:
                print("Redirect response but no location provided.")
                self.failed()
                return
        else:
            print("Failed to download data, HTTP response code: {}".format(response.code))
            self.failed()

    def processData(self, result, filepath, callback, data_type):
        print("*** processData ***")
        try:
            # Directly handle the raw result without decoding it
            if data_type == "json":
                # Decode and process JSON data
                data = result.decode('utf-8') if self.python_version == 3 else result
                self.processJSON(data, filepath, callback)

            elif data_type == "image":
                # Process image data directly
                self.processImage(result, filepath, callback)

            else:
                print("Unsupported data type: {}".format(data_type))

        except Exception as e:
            print("Error processing data: {}".format(e))
            self.failed()

    def processJSON(self, result, filepath, callback):
        print("*** processJSON ***")
        try:
            json_data = json.loads(result)  # No need to decode again, as it's already a string
            with open(filepath, 'w') as json_file:
                json.dump(json_data, json_file)

            callback(json_data)

        except Exception as e:
            print("Error processing JSON or saving file: {}".format(e))
            self.failed()

    def processImage(self, result, filepath, callback):
        print("*** processImage ***")
        try:
            with open(filepath, 'wb') as f:
                f.write(result)  # Write the raw binary data directly

            print("Image saved to {}".format(filepath))
            callback()  # Call the callback after saving the image

        except Exception as e:
            print("Error processing Image or saving file: {}".format(e))
            self.failed()

    def failed(self, error=None):
        print("*** failed ***")
        if error:
            print("Download failed: {}".format(error))
        return

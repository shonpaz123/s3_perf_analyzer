'''
@Author Shon Paz
@Date   7/12/2018
'''

import boto3
import datetime
import time
import humanfriendly
import json
from elasticsearch import Elasticsearch
import socket
import argparse
import uuid

TO_STRING = 'a'

'''This class creates object analyzer objects, these objects are provided with pre-writen attributes and methods 
    relevant for object storage performance analytics'''


class ObjectAnalyzer:

    def __init__(self):

        # creates all needed arguments for the program to run
        parser = argparse.ArgumentParser()
        parser.add_argument('-e', '--endpoint-url', help="endpoint url for s3 object storage", required=True)
        parser.add_argument('-a', '--access-key', help='access key for s3 object storage', required=True)
        parser.add_argument('-s', '--secret-key', help='secret key for s3 object storage', required=True)
        parser.add_argument('-b', '--bucket-name', help='s3 bucket name', required=True)
        parser.add_argument('-o', '--object-size', help='s3 object size', required=True)
        parser.add_argument('-u', '--elastic-url', help='elastic cluster url', required=True)
        parser.add_argument('-n', '--num-objects', help='number of objects to put/get', required=True)
        parser.add_argument('-w', '--workload', help='workload running on s3 - read/write', required=True)

        # parsing all arguments
        args = parser.parse_args()

        # building instance vars
        self.endpoint_url = args.endpoint_url
        self.access_key = args.access_key
        self.secret_key = args.secret_key
        self.bucket_name = args.bucket_name
        self.elastic_cluster = args.elastic_url
        self.object_size = args.object_size
        self.object_name = ""
        self.num_objects = args.num_objects
        self.workload = args.workload
        self.s3 = boto3.client('s3', endpoint_url=self.endpoint_url, aws_access_key_id=self.access_key,
                               aws_secret_access_key=self.secret_key)
        self.elastic = Elasticsearch(self.elastic_cluster)

    ''' This function checks for bucket existence '''
    def check_bucket_existence(self):
        if self.bucket_name in self.s3.list_buckets()['Buckets']:
            return True
        return False

    ''' This function creates bucket according the the user's input '''
    def create_bucket(self):
        self.s3.create_bucket(Bucket=self.bucket_name)

    ''' This function writes an object to object storage using in-memory generated binary data'''
    def put_object(self, object_name, bin_data):
        self.s3.put_object(Key=object_name, Bucket=self.bucket_name, Body=bin_data)

    ''' This function gets an object from object storage'''
    def get_object(self, object_name):
        response = self.s3.get_object(Bucket=self.bucket_name, Key=object_name)
        response['Body'].read()

    ''' This function generates randomized object name'''
    def generate_object_name(self):
        return str(uuid.uuid4())

    ''' This function creates object data according to user's object size input '''
    def create_bin_data(self):
        return humanfriendly.parse_size(self.object_size) * TO_STRING

    ''' This function return number of iterations '''
    def get_objects_num(self):
        return int(self.num_objects)

    ''' This function returns workload'''
    def get_workload(self):
        return self.workload

    def time_operation(self, func):
        start = datetime.datetime.now()
        func
        end = datetime.datetime.now()
        return (end - start).total_seconds() * 1000

    '''This method parses time into kibana timestamp'''
    def create_timestamp(self):
        return round(time.time() * 1000)

    '''This function prepares elasticsearch index for writing '''

    def prepare_elastic_index(self):
        es_index = 's3-perf-index'
        mapping = '''
           {
               "mappings": {
               "doc": {
                   "properties": {
                       "timestamp": {
                       "type": "date"
                           }
                       }
                   }
               }
           }'''
        if not self.elastic.indices.exists(es_index):
            self.elastic.indices.create(index=es_index, body=mapping)

    ''' This function gets a pre-built json and writes it to elasticsearch'''
    def write_elastic_data(self, **kwargs):
        self.elastic.index(index='s3-perf-index', doc_type='doc', body=kwargs)

    ''' This function lists objects in a bucket with a given number '''
    def list_objects(self, max_keys):
        objects = self.s3.list_objects_v2(Bucket=self.bucket_name, MaxKeys=int(max_keys))
        return objects


if __name__ == '__main__':

    # creates an object analyzer instance from class
    object_analyzer = ObjectAnalyzer()

    # prepare elasticsearch index for writing
    object_analyzer.prepare_elastic_index()

    # checks for bucket existence, creates if doesn't exist
    if not object_analyzer.check_bucket_existence():
        object_analyzer.create_bucket()

    # creates binary data
    data = object_analyzer.create_bin_data()

    # verifies that user indeed wants to write
    if object_analyzer.get_workload() == "write":

        # writes wanted number of objects to the bucket
        for index in range(object_analyzer.get_objects_num()):

            # generate new object's name
            object_name = object_analyzer.generate_object_name()

            # time put operation
            latency = object_analyzer.time_operation(object_analyzer.put_object(object_name=object_name,
                                                                                bin_data=data))
            # write data to elasticsearch
            object_analyzer.write_elastic_data(latency=latency,
                                               timestamp=object_analyzer.create_timestamp(),
                                               workload=object_analyzer.get_workload(),
                                               size=object_analyzer.object_size,
                                               object_name=object_name,
                                               source=socket.gethostname())

    elif object_analyzer.get_workload() == "read":

        objects = object_analyzer.list_objects(object_analyzer.num_objects)

        # reads wanted number of objects to the bucket
        for obj in objects['Contents']:

            # sets the object's name
            object_name = obj['Key']

            # gathers latency from get operation
            latency = object_analyzer.time_operation(object_analyzer.get_object(object_name=object_name))

            # write data to elasticsearch
            object_analyzer.write_elastic_data(latency=latency,
                                               timestamp=object_analyzer.create_timestamp(),
                                               workload=object_analyzer.get_workload(),
                                               size=obj['Size'],
                                               object_name=object_name,
                                               source=socket.gethostname())

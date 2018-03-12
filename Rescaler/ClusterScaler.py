#/usr/bin/python
from __future__ import print_function
import sys
import json
import time
import requests
import math
import logging

sys.path.append('..')
import StateDatabase.couchDB as couchDB
import MyUtils.MyUtils as utils

db = couchDB.CouchDBServer()

def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)
	
CONFIG_DEFAULT_VALUES = {"POLLING_FREQUENCY":10, "REQUEST_TIMEOUT":600, "DEBUG":True}
		
def filter_requests(request_timeout):
	filtered_requests = list()
	merged_requests = list()
	all_requests = db.get_requests()
	# First purge the old requests
	for request in all_requests:
		if request["timestamp"] < time.time() - request_timeout:
			db.delete_request(request)
		else:
			filtered_requests.append(request)
	
	# Then remove repeated requests for the same structure if found
	structure_requests_dict = dict()
	for request in filtered_requests:
		structure = request["structure"] # The structure name (string), acting as an id
		action = request["action"] # The action name (string)
		if structure in structure_requests_dict and action in structure_requests_dict[structure]:
			# A previouse request was found for this structure, remove old one and leave the newer one
			stored_request = structure_requests_dict[structure][action]
			if stored_request["timestamp"] > request["timestamp"]:
				# The stored request is newer, leave it and remove the retrieved one
				db.delete_request(request)
			else:
				# The stored request is older, remove it and save the retrieved one
				db.delete_request(stored_request)
				structure_requests_dict[structure][action] = request
		else:
			if not structure in structure_requests_dict:
				structure_requests_dict[structure] = dict()
			structure_requests_dict[structure][action] = request
	
	for structure in structure_requests_dict:
		for action in structure_requests_dict[structure]:
			merged_requests.append(structure_requests_dict[structure][action])

	return merged_requests

def get_container_resources(container):
	r = requests.get("http://dante:8000/container/"+container, headers = {'Accept':'application/json'})
	if r.status_code == 200:
		return dict(r.json())
	else:
		return None


def apply_request(request, resources, specified_resources):
	action = request["action"]
	amount = request["amount"]
	resource_dict = dict()
	resource_dict[request["resource"]] = dict()
	
	if request["resource"] == "cpu":
		resource_dict["cpu"] = dict()
		current_cpu_limit = resources["cpu"]["cpu_allowance_limit"]
		if current_cpu_limit == "-1":
			# CPU is set to unlimited so just apply limit
			current_cpu_limit = specified_resources["max"] # Start with max resources
			#current_cpu_limit = specified_resources["min"] # Start with min resources
			# Careful as values over the max and under the min can be generated with this code
			return None
		else:
			try:
				current_cpu_limit = int(current_cpu_limit)
			except ValueError:
				# Bad value
				return None
		
		effective_cpu_limit = int(resources["cpu"]["effective_num_cpus"])
		cpu_allowance_limit = current_cpu_limit + amount
		
		if cpu_allowance_limit + 100 < effective_cpu_limit or cpu_allowance_limit >= effective_cpu_limit:
			# Round up the number of cores needed as 
			# - at least one core can be reclaimed because of underuse or
			# - not enough cores to apply the limit or close to the limit
			number_of_cpus_requested = int(math.ceil(cpu_allowance_limit / 100.0))
			resource_dict["cpu"]["cpu_num"] = str(range(number_of_cpus_requested)[0]) + "-" +str(range(number_of_cpus_requested)[-1])
		
		resource_dict["cpu"]["cpu_allowance_limit"] = cpu_allowance_limit
		
	elif request["resource"] == "mem":
		current_mem_limit = resources["mem"]["mem_limit"]
		if current_mem_limit == "-1":
			# MEM is set to unlimited so just apply limit
			# FIX
			return None
		else:
			try:
				current_mem_limit = int(current_mem_limit)
			except ValueError:
				# Bad value
				return None
		resource_dict["mem"] = dict()
		resource_dict["mem"]["mem_limit"] = str(int(amount + current_mem_limit)) + 'M'
		
	return resource_dict
	

def set_container_resources(container, resources):
	r = requests.put("http://dante:8000/container/"+container, data=json.dumps(resources), headers = {'Content-Type':'application/json','Accept':'application/json'})
	if r.status_code == 201:
		return dict(r.json())
	else:
		return dict(r.json())
		r.raise_for_status()


def process_request(request, real_resources, specified_resources):
	#Generate the changed_resources document 
	new_resources = apply_request(request, real_resources, specified_resources)
	
	if new_resources:
		logging_info("Request: " + request["action"] + " for container : " + request["structure"] + " for new resources : " + json.dumps(new_resources))
		try:
			structure = request["structure"]
			resource = request["resource"]
			
			# Apply changes through a REST call
			applied_resources = set_container_resources(structure, new_resources)
			
			# Remove the request from the database
			db.delete_request(request)
			
			# Update the limits
			limits = db.get_limits({"name":structure})
			limits["resources"][resource]["upper"] += request["amount"] 
			limits["resources"][resource]["lower"] += request["amount"]
			db.update_doc("limits", limits)
			
			
			# Update the structure current value
			current_value_label = {"cpu":"cpu_allowance_limit", "mem":"mem_limit"}
			updated_structure = db.get_structure(structure)
			updated_structure["resources"][resource]["current"] = applied_resources[resource][current_value_label[resource]]
			db.update_doc("structures", updated_structure)
			
			
		except requests.exceptions.HTTPError as e:
			logging_error(str(e) + " " + str(traceback.format_exc()))
			return


SERVICE_NAME = "scaler"

debug = True
def scale():
	logging.basicConfig(filename='ClusterScaler.log', level=logging.INFO)
	while True:
		service = db.get_service(SERVICE_NAME)
		
		utils.beat(db, SERVICE_NAME)
		
		# CONFIG		
		config = service["config"]
		polling_frequency = utils.get_config_value(config, CONFIG_DEFAULT_VALUES, "POLLING_FREQUENCY")
		request_timeout = utils.get_config_value(config, CONFIG_DEFAULT_VALUES, "REQUEST_TIMEOUT")
		debug = utils.get_config_value(config, CONFIG_DEFAULT_VALUES, "DEBUG")
		
		requests = filter_requests(request_timeout)
		if not requests:
			# No requests to process
			utils.logging_info("No requests at " + utils.get_time_now_string(), debug)
		else:
			logging_info("Requests at " + utils.get_time_now_string())
			for request in requests:
				real_resources = get_container_resources(request["structure"])
				specified_resources = db.get_structure(request["structure"])
				process_request(request, real_resources, specified_resources) 

		time.sleep(polling_frequency)

scale()

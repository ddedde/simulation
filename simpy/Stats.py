# Entities should be able to store information about their trip through the system
# They should also be able to store attributes about themselves (gender, type, age) which could affect their treatment in the system.

# questions:
# How long did this entity spend in the system?
# How long did this entity spend at a particular resource (queue? in service? both combined?)

# primitives for each resource enter queue @ resource -> start processing @ resource -> exit resource
# if we have branches in resources, how do we know which resources an entity touched?
# -- e.g. if we have takeout and dine in as two separate resources.


# Design philosophy: do not hide too much. Things that should be hidden are
# - collection of statistics
# These classes are templates.

import simpy
import numpy as np

from collections import OrderedDict

# This class defines methods to be mixed in to Resource and PriorityResource from simpy. 
class ResourceStatsMixin:
    def __init__(self, env, *args, **kwargs):
        super().__init__(env, *args, **kwargs)
        if self.next_service_time is None:
            raise NotImplementedError("You must define a function called 'next_service_time' in your Resource class")
        self.queue_size = []
        self.env = env

        self.name = self.__class__.__name__

    def request(self, *args, **kwargs):
        req = super().request(*args, **kwargs)
        self.queue_size.append((self.env.now, len(self.queue), 'request'))
        return req

    def release(self, *args, **kwargs):
        return super().release(*args, **kwargs)
    
    def queue_size_over_time(self):
        i = 0
        d = {}
        queue_over_time = []
        for time, size, status in self.queue_size:
            if time in d:
                d[time].append((size, status))
            else:
                d[time] = [(size, status)]
        
        current_queue_size = 0
        for i in range(int(self.env.now)):
            if i in d:
                # we found an activity that happened here
                biggest_size_of_activity = 0
                for size, status in d[i]:
                    if size > biggest_size_of_activity:
                        biggest_size_of_activity = size 
                current_queue_size = biggest_size_of_activity
            queue_over_time.append(current_queue_size)
        
        return queue_over_time
                
    def add_queue_check(self):
        self.queue_size.append((self.env.now, len(self.queue), 'start'))


class Resource(ResourceStatsMixin, simpy.PriorityResource):
    pass

class Entity:

    @staticmethod
    def _empty_resource_tracking_dict():
        return { 'arrival_time': 0, 'start_service_time': 0, 'finish_service_time': 0 }

    def __init__(self, env, attributes):
        """
        resources_requested - keeps track of all of the resources that were requested by this entity (in order of visitation)
        attributes - a list of keys/values that apply to this entity (gender, age, etc...)
        creation_time - when the entity was created (initialized in constructor)
        disposal_time - when the entity was disposed of
        """
        if self.process is None:
             raise NotImplementedError("You must define a function called 'process' in your entity class")
        
        self.attributes = attributes or {}

        # Default priority for non-priority-entities is 0
        priority = 0
        if "priority" in self.attributes.keys():
            priority = self.attributes["priority"]
        elif "priority" in dir(self.__class__):
            priority = self.__class__.priority
        
        self.attributes["priority"] = priority
        self.env = env
        self.creation_time = None
        self.resources_requested = OrderedDict()
        self.disposal_time = None # remember to dispose of entities after finishing processing!

    def set_attribute(self, attribute_name, attribute_value):
        """
        Record arbitrary set of attributes about the entity.
        Could include things like gender, age, anything really.
        Resources might use attributes to determine how a particular entity is processed.
        """
        self.attributes[attribute_name] = attribute_value

    def get_total_time(self):
        """
        total time that the entity spent in the system (from creation to disposal)
        only accessible once the entity has been disposed
        """
        if self.is_disposed():
            self._calculate_statistics()
            return self.total_time
        else:
            raise Exception("Can't get total time: Entity has not been disposed")

    def get_total_waiting_time(self):
        """
        total time that the entity spent queued waiting for resources
        only accessible wonce the entity has been disposed
        """
        if self.is_disposed():
            self._calculate_statistics()
            return self.waiting_time
        else:
            raise Exception("Can't get total waiting time: Entity has not been disposed")

    def get_waiting_time_for_resource(self, resource):
        """
        time that the entity spent waiting for a particular resource
        """
        return self._calculate_waiting_time_for_resource(resource.name)

    def get_total_processing_time(self):
        """
        total time that the entity spent being processed by resources
        """
        if self.is_disposed():
            self._calculate_statistics()
            return self.processing_time
        else:
            raise Exception("Can't get total processing time: Entity has not been disposed")

    def get_processing_time_for_resource(self, resource):
        """
        time that the entity spent being processed by a particular resource
        """
        return self._calculate_processing_time_for_resource(resource.name)

    def request_resource(self, resource):
        """
        The time that a resource is requested
        should be logged as the "arrival time" for the resource.
        """
        print(f'{self.name} requesting {resource.name}: {self.env.now}')

        self._add_resource_to_visited(resource.name)
        self.resources_requested[resource.name]["arrival_time"] = self.env.now
        return resource.request(priority=self.attributes["priority"] if 'priority' in self.attributes.keys() else None)
    
    def start_service_at_resource(self, resource):
        print(f'{self.name} started processing at {resource.name} : {self.env.now}')        
        self.resources_requested[resource.name]["start_service_time"] = self.env.now
        resource.add_queue_check()

    def release_resource(self, resource, request):
        print(f'{self.name} finished at {resource.name}: {self.env.now}')
        self.resources_requested[resource.name]["finish_service_time"] = self.env.now
        resource.release(request)

    def dispose(self):
        """
        After an entity is finished being processed, it should be disposed
        """
        self.disposal_time = self.env.now
        print(f"{self.name} disposed: {self.disposal_time}")
        return self.disposal_time
    
    def __str__(self):
        return f"{self.name} created_at: {self.creation_time} attributes: {self.attributes}"

    def is_disposed(self):
        return self.disposal_time is not None

    def _calculate_waiting_time_for_resource(self, resource_name):
        resource_stats = self.resources_requested[resource_name]
        return resource_stats["start_service_time"] - resource_stats["arrival_time"]

    def _calculate_processing_time_for_resource(self, resource_name):
        resource_stats = self.resources_requested[resource_name]
        return resource_stats["finish_service_time"] - resource_stats["start_service_time"]

    def _calculate_statistics(self):
        if not self.is_disposed():
            raise Exception("Entity is not yet disposed. Dispose of this entity before calculating stats")
        waiting_time = 0
        processing_time = 0
        for resource_name, _ in self.resources_requested.items():
            waiting_time += self._calculate_waiting_time_for_resource(resource_name)
            processing_time += self._calculate_processing_time_for_resource(resource_name)

        self.total_time = self.disposal_time - self.creation_time
        self.waiting_time = waiting_time
        self.processing_time = processing_time

    def _add_resource_to_visited(self, resource_name):
        self.resources_requested[resource_name] = Entity._empty_resource_tracking_dict()


class Source:
    """
    keeps track of entities that have been produced for simluation
    """
    def __init__(self, env, first_creation=None, number=float("Inf"), *args, **kwargs):
        try:
            self._interarrival_time_generator_template = self.interarrival_time_generator()
        except AttributeError:
            raise NotImplementedError("Provide a method named interarrival_time_generator on your Source Class")
        self.env = env
        self.first_creation = first_creation
        self.number = number
        self.entities = []
        self.count = 0

    def next_entity(self, *args, **kwargs):
        for time in self._interarrival_time_generator():
            self.count += 1
            if len(self.entities) == self.number:
                # we've reached the number we need to source
                # They will finish processing before simulation ends
                break 
            timeout = self.env.timeout(time)
            creation_time = self.env.now + time
            entity = self.build_entity()
            entity.creation_time = creation_time
            entity.name = f"{entity.__class__.__name__} {self.count}"
            self.entities.append(entity)
            yield timeout, entity        
    
    def get_total_times(self):
        return [entity.get_total_time() for entity in self._get_disposed_entities()]

    def get_waiting_times(self):
        return [entity.get_total_waiting_time() for entity in self._get_disposed_entities()]
    
    def get_processing_times(self):
        return [entity.get_total_processing_time() for entity in self._get_disposed_entities()]
    
    # private methods
    
    def _get_disposed_entities(self):
        return [entity for entity in self.entities if entity.is_disposed()]
    
    def _interarrival_time_generator(self):
        # if first_creation exists, emit it as the first time, else just use the interarrival_time
        if self.first_creation is not None:
            yield self.first_creation
        for time in self._interarrival_time_generator_template:
            yield time
    
from importlib import import_module

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers

from task_api.models import TaskInfo
from task_api.params import ParameterNotValidError

BACKGROUND_TASKS = getattr(settings, 'BACKGROUND_TASKS', [])


class TaskInfoSerializer(serializers.ModelSerializer):
    inputs = serializers.DictField(allow_null=True)
    outputs = serializers.DictField(read_only=True)

    class Meta:
        model = TaskInfo
        fields = ('uuid', 'task', 'status', 'progress', 'target', 'inputs', 'outputs', 'created', 'started', 'finished')
        read_only_fields = ('uuid', 'status', 'progress', 'target', 'outputs', 'created', 'started', 'finished')

    def get_task_cls(self, task):
        for class_str in BACKGROUND_TASKS:
            try:
                module_name, class_name = class_str.rsplit('.', 1)
                module = import_module(module_name)
                cls = getattr(module, class_name)
            except (ImportError, ValueError, AttributeError):
                raise ImproperlyConfigured('Cannot find background task: ' + class_str)
            if cls.name == task:
                return cls
        return None

    def validate_task(self, value):
        if self.get_task_cls(value) is not None:
            return value
        else:
            raise serializers.ValidationError('Invalid task')

    def validate(self, data):
        task_cls = self.get_task_cls(data['task'])
        missing_params = set(k for k, v in task_cls.inputs.items() if v.required).difference(set(data['inputs'].keys()))

        if missing_params:
            raise serializers.ValidationError('Missing task inputs: {}'.format(','.join(missing_params)))

        for name, param in task_cls.inputs.items():
            if name not in data['inputs']:
                continue
            try:
                param.to_python(data['inputs'][name])
            except ParameterNotValidError as ex:
                raise serializers.ValidationError("Input '{}' is invalid: {}".format(name, str(ex)))

        return data

    def create(self, validated_data):
        self.get_task_cls(validated_data['task']).start(validated_data['inputs'])

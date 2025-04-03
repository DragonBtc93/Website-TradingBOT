cimport cython
from dataclasses import dataclass, field
from typing import (
    AbstractSet,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    Union,
)

from apischema.aliases import Aliaser
from apischema.conversions.utils import Converter
from apischema.deserialization.coercion import Coercer
from apischema.json_schema.types import bad_type
from apischema.types import AnyType, NoneType
from apischema.utils import Lazy
from apischema.validation.errors import (
    ErrorKey,
    ErrorMsg,
    ValidationError,
    merge_errors,
)
from apischema.validation.mock import ValidatorMock
from apischema.validation.validators import Validator, validate


cdef class Constraint():
    cdef readonly object error
    cdef int _dispatch

    def __init__(self, error):
        self.error = error

cdef class MinimumConstraint(Constraint):
    cdef readonly long minimum

    cpdef validate(self, object data):
        return MinimumConstraint_validate(self, data)

    def __init__(self, error, minimum):
        self.error = error
        self.minimum = minimum
        self._dispatch = 0

cdef class MaximumConstraint(Constraint):
    cdef readonly long maximum

    cpdef validate(self, object data):
        return MaximumConstraint_validate(self, data)

    def __init__(self, error, maximum):
        self.error = error
        self.maximum = maximum
        self._dispatch = 1

cdef class ExclusiveMinimumConstraint(Constraint):
    cdef readonly long exc_min

    cpdef validate(self, object data):
        return ExclusiveMinimumConstraint_validate(self, data)

    def __init__(self, error, exc_min):
        self.error = error
        self.exc_min = exc_min
        self._dispatch = 2

cdef class ExclusiveMaximumConstraint(Constraint):
    cdef readonly long exc_max

    cpdef validate(self, object data):
        return ExclusiveMaximumConstraint_validate(self, data)

    def __init__(self, error, exc_max):
        self.error = error
        self.exc_max = exc_max
        self._dispatch = 3

cdef class MultipleOfConstraint(Constraint):
    cdef readonly long mult_of

    cpdef validate(self, object data):
        return MultipleOfConstraint_validate(self, data)

    def __init__(self, error, mult_of):
        self.error = error
        self.mult_of = mult_of
        self._dispatch = 4

cdef class MinLengthConstraint(Constraint):
    cdef readonly long min_len

    cpdef validate(self, object data):
        return MinLengthConstraint_validate(self, data)

    def __init__(self, error, min_len):
        self.error = error
        self.min_len = min_len
        self._dispatch = 5

cdef class MaxLengthConstraint(Constraint):
    cdef readonly long max_len

    cpdef validate(self, object data):
        return MaxLengthConstraint_validate(self, data)

    def __init__(self, error, max_len):
        self.error = error
        self.max_len = max_len
        self._dispatch = 6

cdef class PatternConstraint(Constraint):
    cdef readonly object pattern

    cpdef validate(self, object data):
        return PatternConstraint_validate(self, data)

    def __init__(self, error, pattern):
        self.error = error
        self.pattern = pattern
        self._dispatch = 7

cdef class MinItemsConstraint(Constraint):
    cdef readonly long min_items

    cpdef validate(self, object data):
        return MinItemsConstraint_validate(self, data)

    def __init__(self, error, min_items):
        self.error = error
        self.min_items = min_items
        self._dispatch = 8

cdef class MaxItemsConstraint(Constraint):
    cdef readonly long max_items

    cpdef validate(self, object data):
        return MaxItemsConstraint_validate(self, data)

    def __init__(self, error, max_items):
        self.error = error
        self.max_items = max_items
        self._dispatch = 9

cdef class UniqueItemsConstraint(Constraint):
    cdef readonly bint unique

    cpdef validate(self, object data):
        return UniqueItemsConstraint_validate(self, data)

    def __init__(self, error, unique):
        self.error = error
        self.unique = unique
        assert self.unique
        self._dispatch = 10

cdef class MinPropertiesConstraint(Constraint):
    cdef readonly long min_properties

    cpdef validate(self, object data):
        return MinPropertiesConstraint_validate(self, data)

    def __init__(self, error, min_properties):
        self.error = error
        self.min_properties = min_properties
        self._dispatch = 11

cdef class MaxPropertiesConstraint(Constraint):
    cdef readonly long max_properties

    cpdef validate(self, object data):
        return MaxPropertiesConstraint_validate(self, data)

    def __init__(self, error, max_properties):
        self.error = error
        self.max_properties = max_properties
        self._dispatch = 12

cdef class DeserializationMethod():
    cdef int _dispatch

cdef class RecMethod(DeserializationMethod):
    cdef readonly object lazy
    cdef readonly object method

    cpdef deserialize(self, object data):
        return RecMethod_deserialize(self, data)

    def __init__(self, lazy):
        self.lazy = lazy
        self.method = None
        self._dispatch = 0

cdef class ValidatorMethod(DeserializationMethod):
    cdef readonly DeserializationMethod method
    cdef readonly object validators
    cdef readonly object aliaser

    cpdef deserialize(self, object data):
        return ValidatorMethod_deserialize(self, data)

    def __init__(self, method, validators, aliaser):
        self.method = method
        self.validators = validators
        self.aliaser = aliaser
        self._dispatch = 1

cdef class CoercerMethod(DeserializationMethod):
    cdef readonly object coercer
    cdef readonly type cls
    cdef readonly DeserializationMethod method

    cpdef deserialize(self, object data):
        return CoercerMethod_deserialize(self, data)

    def __init__(self, coercer, cls, method):
        self.coercer = coercer
        self.cls = cls
        self.method = method
        self._dispatch = 2

cdef class TypeCheckMethod(DeserializationMethod):
    cdef readonly object expected
    cdef readonly DeserializationMethod fallback

    cpdef deserialize(self, object data):
        return TypeCheckMethod_deserialize(self, data)

    def __init__(self, expected, fallback):
        self.expected = expected
        self.fallback = fallback
        self._dispatch = 3

cdef class AnyMethod(DeserializationMethod):
    cdef readonly dict constraints

    cpdef deserialize(self, object data):
        return AnyMethod_deserialize(self, data)

    def __init__(self, constraints):
        self.constraints = constraints
        self._dispatch = 4

cdef class ListCheckOnlyMethod(DeserializationMethod):
    cdef readonly tuple constraints
    cdef readonly DeserializationMethod value_method

    cpdef deserialize(self, object data):
        return ListCheckOnlyMethod_deserialize(self, data)

    def __init__(self, constraints, value_method):
        self.constraints = constraints
        self.value_method = value_method
        self._dispatch = 5

cdef class ListMethod(DeserializationMethod):
    cdef readonly tuple constraints
    cdef readonly DeserializationMethod value_method

    cpdef deserialize(self, object data):
        return ListMethod_deserialize(self, data)

    def __init__(self, constraints, value_method):
        self.constraints = constraints
        self.value_method = value_method
        self._dispatch = 6

cdef class SetMethod(DeserializationMethod):
    cdef readonly tuple constraints
    cdef readonly DeserializationMethod value_method

    cpdef deserialize(self, object data):
        return SetMethod_deserialize(self, data)

    def __init__(self, constraints, value_method):
        self.constraints = constraints
        self.value_method = value_method
        self._dispatch = 7

cdef class FrozenSetMethod(DeserializationMethod):
    cdef readonly DeserializationMethod method

    cpdef deserialize(self, object data):
        return FrozenSetMethod_deserialize(self, data)

    def __init__(self, method):
        self.method = method
        self._dispatch = 8

cdef class VariadicTupleMethod(DeserializationMethod):
    cdef readonly DeserializationMethod method

    cpdef deserialize(self, object data):
        return VariadicTupleMethod_deserialize(self, data)

    def __init__(self, method):
        self.method = method
        self._dispatch = 9

cdef class LiteralMethod(DeserializationMethod):
    cdef readonly dict value_map
    cdef readonly object error
    cdef readonly object coercer
    cdef readonly tuple types

    cpdef deserialize(self, object data):
        return LiteralMethod_deserialize(self, data)

    def __init__(self, value_map, error, coercer, types):
        self.value_map = value_map
        self.error = error
        self.coercer = coercer
        self.types = types
        self._dispatch = 10

cdef class MappingCheckOnly(DeserializationMethod):
    cdef readonly tuple constraints
    cdef readonly DeserializationMethod key_method
    cdef readonly DeserializationMethod value_method

    cpdef deserialize(self, object data):
        return MappingCheckOnly_deserialize(self, data)

    def __init__(self, constraints, key_method, value_method):
        self.constraints = constraints
        self.key_method = key_method
        self.value_method = value_method
        self._dispatch = 11

cdef class MappingMethod(DeserializationMethod):
    cdef readonly tuple constraints
    cdef readonly DeserializationMethod key_method
    cdef readonly DeserializationMethod value_method

    cpdef deserialize(self, object data):
        return MappingMethod_deserialize(self, data)

    def __init__(self, constraints, key_method, value_method):
        self.constraints = constraints
        self.key_method = key_method
        self.value_method = value_method
        self._dispatch = 12

cdef class Field():
    cdef readonly str name
    cdef readonly str alias
    cdef readonly DeserializationMethod method
    cdef readonly bint required
    cdef readonly object required_by
    cdef readonly bint fall_back_on_default

    def __init__(self, name, alias, method, required, required_by, fall_back_on_default):
        self.name = name
        self.alias = alias
        self.method = method
        self.required = required
        self.required_by = required_by
        self.fall_back_on_default = fall_back_on_default

cdef class FlattenedField():
    cdef readonly str name
    cdef readonly tuple aliases
    cdef readonly DeserializationMethod method
    cdef readonly bint fall_back_on_default

    def __init__(self, name, aliases, method, fall_back_on_default):
        self.name = name
        self.aliases = aliases
        self.method = method
        self.fall_back_on_default = fall_back_on_default

cdef class PatternField():
    cdef readonly str name
    cdef readonly object pattern
    cdef readonly DeserializationMethod method
    cdef readonly bint fall_back_on_default

    def __init__(self, name, pattern, method, fall_back_on_default):
        self.name = name
        self.pattern = pattern
        self.method = method
        self.fall_back_on_default = fall_back_on_default

cdef class AdditionalField():
    cdef readonly str name
    cdef readonly DeserializationMethod method
    cdef readonly bint fall_back_on_default

    def __init__(self, name, method, fall_back_on_default):
        self.name = name
        self.method = method
        self.fall_back_on_default = fall_back_on_default

cdef class Constructor():
    cdef readonly object cls
    cdef int _dispatch

    def __init__(self, cls):
        self.cls = cls

cdef class NoConstructor(Constructor):

    cpdef construct(self, dict fields):
        return NoConstructor_construct(self, fields)

    def __init__(self, cls):
        self.cls = cls
        self._dispatch = 0

cdef class RawConstructor(Constructor):

    cpdef construct(self, dict fields):
        return RawConstructor_construct(self, fields)

    def __init__(self, cls):
        self.cls = cls
        self._dispatch = 1

cdef class DefaultField():
    cdef readonly str name
    cdef readonly object default_value

    def __init__(self, name, default_value):
        self.name = name
        self.default_value = default_value

cdef class FactoryField():
    cdef readonly str name
    cdef readonly object factory

    def __init__(self, name, factory):
        self.name = name
        self.factory = factory

cdef class FieldsConstructor(Constructor):
    cdef readonly long nb_fields
    cdef readonly tuple default_fields
    cdef readonly tuple factory_fields

    cpdef construct(self, dict fields):
        return FieldsConstructor_construct(self, fields)

    def __init__(self, cls, nb_fields, default_fields, factory_fields):
        self.cls = cls
        self.nb_fields = nb_fields
        self.default_fields = default_fields
        self.factory_fields = factory_fields
        self._dispatch = 2

cdef class SimpleObjectMethod(DeserializationMethod):
    cdef readonly Constructor constructor
    cdef readonly tuple fields
    cdef readonly set all_aliases
    cdef readonly bint typed_dict
    cdef readonly str missing
    cdef readonly str unexpected

    cpdef deserialize(self, object data):
        return SimpleObjectMethod_deserialize(self, data)

    def __init__(self, constructor, fields, all_aliases, typed_dict, missing, unexpected):
        self.constructor = constructor
        self.fields = fields
        self.all_aliases = all_aliases
        self.typed_dict = typed_dict
        self.missing = missing
        self.unexpected = unexpected
        self._dispatch = 13

cdef class ObjectMethod(DeserializationMethod):
    cdef readonly Constructor constructor
    cdef readonly tuple constraints
    cdef readonly tuple fields
    cdef readonly tuple flattened_fields
    cdef readonly tuple pattern_fields
    cdef readonly object additional_field
    cdef readonly set all_aliases
    cdef readonly bint additional_properties
    cdef readonly bint typed_dict
    cdef readonly tuple validators
    cdef readonly tuple init_defaults
    cdef readonly set post_init_modified
    cdef readonly object aliaser
    cdef readonly str missing
    cdef readonly str unexpected
    cdef readonly object discriminator
    cdef readonly bint aggregate_fields

    cpdef deserialize(self, object data):
        return ObjectMethod_deserialize(self, data)

    def __init__(self, constructor, constraints, fields, flattened_fields, pattern_fields, additional_field, all_aliases, additional_properties, typed_dict, validators, init_defaults, post_init_modified, aliaser, missing, unexpected, discriminator):
        self.constructor = constructor
        self.constraints = constraints
        self.fields = fields
        self.flattened_fields = flattened_fields
        self.pattern_fields = pattern_fields
        self.additional_field = additional_field
        self.all_aliases = all_aliases
        self.additional_properties = additional_properties
        self.typed_dict = typed_dict
        self.validators = validators
        self.init_defaults = init_defaults
        self.post_init_modified = post_init_modified
        self.aliaser = aliaser
        self.missing = missing
        self.unexpected = unexpected
        self.discriminator = discriminator
        self.aggregate_fields = bool(
            self.flattened_fields
            or self.pattern_fields
            or self.additional_field is not None
        )
        self._dispatch = 14

cdef class NoneMethod(DeserializationMethod):

    cpdef deserialize(self, object data):
        return NoneMethod_deserialize(self, data)

    def __init__(self):
        self._dispatch = 15

cdef class IntMethod(DeserializationMethod):

    cpdef deserialize(self, object data):
        return IntMethod_deserialize(self, data)

    def __init__(self):
        self._dispatch = 16

cdef class FloatMethod(DeserializationMethod):

    cpdef deserialize(self, object data):
        return FloatMethod_deserialize(self, data)

    def __init__(self):
        self._dispatch = 18

cdef class StrMethod(DeserializationMethod):

    cpdef deserialize(self, object data):
        return StrMethod_deserialize(self, data)

    def __init__(self):
        self._dispatch = 20

cdef class BoolMethod(DeserializationMethod):

    cpdef deserialize(self, object data):
        return BoolMethod_deserialize(self, data)

    def __init__(self):
        self._dispatch = 22

cdef class ConstrainedIntMethod(IntMethod):
    cdef readonly tuple constraints

    cpdef deserialize(self, object data):
        return ConstrainedIntMethod_deserialize(self, data)

    def __init__(self, constraints):
        self.constraints = constraints
        self._dispatch = 17

cdef class ConstrainedFloatMethod(FloatMethod):
    cdef readonly tuple constraints

    cpdef deserialize(self, object data):
        return ConstrainedFloatMethod_deserialize(self, data)

    def __init__(self, constraints):
        self.constraints = constraints
        self._dispatch = 19

cdef class ConstrainedStrMethod(StrMethod):
    cdef readonly tuple constraints

    cpdef deserialize(self, object data):
        return ConstrainedStrMethod_deserialize(self, data)

    def __init__(self, constraints):
        self.constraints = constraints
        self._dispatch = 21

cdef class SubprimitiveMethod(DeserializationMethod):
    cdef readonly type cls
    cdef readonly DeserializationMethod method

    cpdef deserialize(self, object data):
        return SubprimitiveMethod_deserialize(self, data)

    def __init__(self, cls, method):
        self.cls = cls
        self.method = method
        self._dispatch = 23

cdef class TupleMethod(DeserializationMethod):
    cdef readonly tuple constraints
    cdef readonly object min_len_error
    cdef readonly object max_len_error
    cdef readonly tuple elt_methods

    cpdef deserialize(self, object data):
        return TupleMethod_deserialize(self, data)

    def __init__(self, constraints, min_len_error, max_len_error, elt_methods):
        self.constraints = constraints
        self.min_len_error = min_len_error
        self.max_len_error = max_len_error
        self.elt_methods = elt_methods
        self._dispatch = 24

cdef class OptionalMethod(DeserializationMethod):
    cdef readonly DeserializationMethod value_method
    cdef readonly object coercer

    cpdef deserialize(self, object data):
        return OptionalMethod_deserialize(self, data)

    def __init__(self, value_method, coercer):
        self.value_method = value_method
        self.coercer = coercer
        self._dispatch = 25

cdef class UnionByTypeMethod(DeserializationMethod):
    cdef readonly dict method_by_cls

    cpdef deserialize(self, object data):
        return UnionByTypeMethod_deserialize(self, data)

    def __init__(self, method_by_cls):
        self.method_by_cls = method_by_cls
        self._dispatch = 26

cdef class UnionMethod(DeserializationMethod):
    cdef readonly tuple alt_methods

    cpdef deserialize(self, object data):
        return UnionMethod_deserialize(self, data)

    def __init__(self, alt_methods):
        self.alt_methods = alt_methods
        self._dispatch = 27

cdef class ConversionMethod(DeserializationMethod):
    cdef readonly object converter
    cdef readonly DeserializationMethod method

    cpdef deserialize(self, object data):
        return ConversionMethod_deserialize(self, data)

    def __init__(self, converter, method):
        self.converter = converter
        self.method = method
        self._dispatch = 28

cdef class ConversionWithValueErrorMethod(ConversionMethod):

    cpdef deserialize(self, object data):
        return ConversionWithValueErrorMethod_deserialize(self, data)

    def __init__(self, converter, method):
        self.converter = converter
        self.method = method
        self._dispatch = 29

cdef class ConversionAlternative():
    cdef readonly object converter
    cdef readonly DeserializationMethod method
    cdef readonly bint value_error

    def __init__(self, converter, method, value_error):
        self.converter = converter
        self.method = method
        self.value_error = value_error

cdef class ConversionUnionMethod(DeserializationMethod):
    cdef readonly tuple alternatives

    cpdef deserialize(self, object data):
        return ConversionUnionMethod_deserialize(self, data)

    def __init__(self, alternatives):
        self.alternatives = alternatives
        self._dispatch = 30

cdef class DiscriminatorMethod(DeserializationMethod):
    cdef readonly str alias
    cdef readonly dict mapping
    cdef readonly str missing
    cdef readonly object error

    cpdef deserialize(self, object data):
        return DiscriminatorMethod_deserialize(self, data)

    def __init__(self, alias, mapping, missing, error):
        self.alias = alias
        self.mapping = mapping
        self.missing = missing
        self.error = error
        self._dispatch = 31

cpdef inline to_hashable(object data):
    if isinstance(data, list):
        return tuple(map(to_hashable, data))
    elif isinstance(data, dict):
        # Cython doesn't support tuple comprehension yet -> intermediate list
        return tuple([(k, to_hashable(data[k])) for k in sorted(data)])
    else:
        return data

cpdef inline format_error(object err, object data):
    return err if isinstance(err, str) else err(data)

cpdef inline validate_constraints(object data, tuple constraints, object children_errors):
    for i in range(len(constraints)):
        constraint: Constraint = constraints[i]
        if not Constraint_validate(constraint, data):
            errors: list = [format_error(constraint.error, data)]
            for j in range(i + 1, len(constraints)):
                constraint = constraints[j]
                if not Constraint_validate(constraint, data):
                    errors.append(format_error(constraint.error, data))
            raise ValidationError(errors, children_errors or {})
    if children_errors:
        raise ValidationError([], children_errors)
    return data

cpdef inline set_child_error(object errors, object key, object error):
    if errors is None:
        return {key: error}
    else:
        errors[key] = error
        return errors

cpdef inline extend_errors(object errors, object messages):
    if errors is None:
        return list(messages)
    else:
        errors.extend(messages)
        return errors

cpdef inline update_children_errors(object errors, dict children):
    if errors is None:
        return dict(children)
    else:
        errors.update(children)
        return errors

cdef inline MinimumConstraint_validate(MinimumConstraint self, long data):
        return data >= self.minimum

cdef inline MaximumConstraint_validate(MaximumConstraint self, long data):
        return data <= self.maximum

cdef inline ExclusiveMinimumConstraint_validate(ExclusiveMinimumConstraint self, long data):
        return data > self.exc_min

cdef inline ExclusiveMaximumConstraint_validate(ExclusiveMaximumConstraint self, long data):
        return data < self.exc_max

cdef inline MultipleOfConstraint_validate(MultipleOfConstraint self, long data):
        return not (data % self.mult_of)

cdef inline MinLengthConstraint_validate(MinLengthConstraint self, str data):
        return len(data) >= self.min_len

cdef inline MaxLengthConstraint_validate(MaxLengthConstraint self, str data):
        return len(data) <= self.max_len

cdef inline PatternConstraint_validate(PatternConstraint self, str data):
        return self.pattern.match(data) is not None

cdef inline MinItemsConstraint_validate(MinItemsConstraint self, list data):
        return len(data) >= self.min_items

cdef inline MaxItemsConstraint_validate(MaxItemsConstraint self, list data):
        return len(data) <= self.max_items

cdef inline UniqueItemsConstraint_validate(UniqueItemsConstraint self, list data):
        return len(set(map(to_hashable, data))) == len(data)

cdef inline MinPropertiesConstraint_validate(MinPropertiesConstraint self, dict data):
        return len(data) >= self.min_properties

cdef inline MaxPropertiesConstraint_validate(MaxPropertiesConstraint self, dict data):
        return len(data) <= self.max_properties

cdef inline RecMethod_deserialize(RecMethod self, object data):
        if self.method is None:
            self.method = self.lazy()
        return DeserializationMethod_deserialize(self.method, data)

cdef inline ValidatorMethod_deserialize(ValidatorMethod self, object data):
        return validate(
            DeserializationMethod_deserialize(self.method, data), self.validators, aliaser=self.aliaser
        )

cdef inline CoercerMethod_deserialize(CoercerMethod self, object data):
        return DeserializationMethod_deserialize(self.method, self.coercer(self.cls, data))

cdef inline TypeCheckMethod_deserialize(TypeCheckMethod self, object data):
        if isinstance(data, self.expected):
            return data
        return DeserializationMethod_deserialize(self.fallback, data)

cdef inline AnyMethod_deserialize(AnyMethod self, object data):
        if type(data) in self.constraints:
            validate_constraints(data, self.constraints[type(data)], None)
        return data

cdef inline ListCheckOnlyMethod_deserialize(ListCheckOnlyMethod self, object data):
        if not isinstance(data, list):
            raise bad_type(data, list)
        elt_errors = None
        for i, elt in enumerate(data):
            try:
                DeserializationMethod_deserialize(self.value_method, elt)
            except ValidationError as err:
                elt_errors = set_child_error(elt_errors, i, err)
        validate_constraints(data, self.constraints, elt_errors)
        return data

cdef inline ListMethod_deserialize(ListMethod self, object data):
        if not isinstance(data, list):
            raise bad_type(data, list)
        elt_errors = None
        values: list = [None] * len(data)
        for i, elt in enumerate(data):
            try:
                values[i] = DeserializationMethod_deserialize(self.value_method, elt)
            except ValidationError as err:
                elt_errors = set_child_error(elt_errors, i, err)
        validate_constraints(data, self.constraints, elt_errors)
        return values

cdef inline SetMethod_deserialize(SetMethod self, object data):
        if not isinstance(data, list):
            raise bad_type(data, list)
        elt_errors: dict = {}
        values: set = set()
        for i, elt in enumerate(data):
            try:
                values.add(DeserializationMethod_deserialize(self.value_method, elt))
            except ValidationError as err:
                elt_errors = set_child_error(elt_errors, i, err)
        validate_constraints(data, self.constraints, elt_errors)
        return values

cdef inline FrozenSetMethod_deserialize(FrozenSetMethod self, object data):
        return frozenset(DeserializationMethod_deserialize(self.method, data))

cdef inline VariadicTupleMethod_deserialize(VariadicTupleMethod self, object data):
        return tuple(DeserializationMethod_deserialize(self.method, data))

cdef inline LiteralMethod_deserialize(LiteralMethod self, object data):
        try:
            return self.value_map[data]
        except KeyError:
            if self.coercer is not None:
                for cls in self.types:
                    try:
                        return self.value_map[self.coercer(cls, data)]
                    except IndexError:
                        pass
            raise ValidationError(format_error(self.error, data))
        except TypeError:
            raise bad_type(data, *self.types)

cdef inline MappingCheckOnly_deserialize(MappingCheckOnly self, object data):
        if not isinstance(data, dict):
            raise bad_type(data, dict)
        item_errors = None
        for key, value in data.items():
            try:
                DeserializationMethod_deserialize(self.key_method, key)
                DeserializationMethod_deserialize(self.value_method, value)
            except ValidationError as err:
                item_errors = set_child_error(item_errors, key, err)
        validate_constraints(data, self.constraints, item_errors)
        return data

cdef inline MappingMethod_deserialize(MappingMethod self, object data):
        if not isinstance(data, dict):
            raise bad_type(data, dict)
        item_errors = None
        items: dict = {}
        for key, value in data.items():
            try:
                items[DeserializationMethod_deserialize(self.key_method, key)] = DeserializationMethod_deserialize(self.value_method, 
                    value
                )
            except ValidationError as err:
                item_errors = set_child_error(item_errors, key, err)
        validate_constraints(data, self.constraints, item_errors)
        return items

cdef inline SimpleObjectMethod_deserialize(SimpleObjectMethod self, object data):
        if not isinstance(data, dict):
            raise bad_type(data, dict)
        fields_count = 0
        field_errors = None
        for i in range(len(self.fields)):
            field: Field = self.fields[i]
            if field.alias in data:
                fields_count += 1
                try:
                    DeserializationMethod_deserialize(field.method, data[field.alias])
                except ValidationError as err:
                    if field.required or not field.fall_back_on_default:
                        field_errors = set_child_error(field_errors, field.alias, err)
            elif field.required:
                field_errors = set_child_error(
                    field_errors, field.alias, ValidationError(self.missing)
                )
        if len(data) != fields_count and not self.typed_dict:
            for key in data.keys() - self.all_aliases:
                field_errors = set_child_error(
                    field_errors, key, ValidationError(self.unexpected)
                )
        if field_errors:
            raise ValidationError([], field_errors)
        return Constructor_construct(self.constructor, data)

cdef inline ObjectMethod_deserialize(ObjectMethod self, object data):
        if not isinstance(data, dict):
            raise bad_type(data, dict)
        values: dict = {}
        fields_count = 0
        errors = None
        try:
            validate_constraints(data, self.constraints, None)
        except ValidationError as err:
            errors = list(err.messages)
        field_errors = None
        for i in range(len(self.fields)):
            field: Field = self.fields[i]
            if field.required:
                try:
                    value: object = data[field.alias]
                except KeyError:
                    field_errors = set_child_error(
                        field_errors, field.alias, ValidationError(self.missing)
                    )
                else:
                    fields_count += 1
                    try:
                        values[field.name] = DeserializationMethod_deserialize(field.method, value)
                    except ValidationError as err:
                        field_errors = set_child_error(field_errors, field.alias, err)
            elif field.alias in data:
                fields_count += 1
                try:
                    values[field.name] = DeserializationMethod_deserialize(field.method, data[field.alias])
                except ValidationError as err:
                    if not field.fall_back_on_default:
                        field_errors = set_child_error(field_errors, field.alias, err)
            elif field.required_by is not None and not field.required_by.isdisjoint(
                data
            ):
                requiring: list = sorted(field.required_by & data.keys())
                msg: str = self.missing + f" (required by {requiring})"
                field_errors = set_child_error(
                    field_errors, field.alias, ValidationError([msg])
                )
        if self.aggregate_fields:
            remain = data.keys() - self.all_aliases
            for i in range(len(self.flattened_fields)):
                flattened_field: FlattenedField = self.flattened_fields[i]
                flattened: dict = {
                    alias: data[alias]
                    for alias in flattened_field.aliases
                    if alias in data
                }
                remain.difference_update(flattened)
                try:
                    values[flattened_field.name] = DeserializationMethod_deserialize(flattened_field.method, 
                        flattened
                    )
                except ValidationError as err:
                    if not flattened_field.fall_back_on_default:
                        errors = extend_errors(errors, err.messages)
                        field_errors = update_children_errors(
                            field_errors, err.children
                        )
            for i in range(len(self.pattern_fields)):
                pattern_field: PatternField = self.pattern_fields[i]
                matched: dict = {
                    key: data[key] for key in remain if pattern_field.pattern.match(key)
                }
                remain.difference_update(matched)
                try:
                    values[pattern_field.name] = DeserializationMethod_deserialize(pattern_field.method, 
                        matched
                    )
                except ValidationError as err:
                    if not pattern_field.fall_back_on_default:
                        errors = extend_errors(errors, err.messages)
                        field_errors = update_children_errors(
                            field_errors, err.children
                        )
            if self.additional_field is not None:
                additional: dict = {key: data[key] for key in remain}
                try:
                    values[
                        self.additional_field.name
                    ] = DeserializationMethod_deserialize(self.additional_field.method, additional)
                except ValidationError as err:
                    if not self.additional_field.fall_back_on_default:
                        errors = extend_errors(errors, err.messages)
                        field_errors = update_children_errors(
                            field_errors, err.children
                        )
            elif remain:
                if not self.additional_properties:
                    for key in remain:
                        if key != self.discriminator:
                            field_errors = set_child_error(
                                field_errors, key, ValidationError(self.unexpected)
                            )
                elif self.typed_dict:
                    for key in remain:
                        values[key] = data[key]
        elif len(data) != fields_count:
            if not self.additional_properties:
                for key in data.keys() - self.all_aliases:
                    if key != self.discriminator:
                        field_errors = set_child_error(
                            field_errors, key, ValidationError(self.unexpected)
                        )
            elif self.typed_dict:
                for key in data.keys() - self.all_aliases:
                    values[key] = data[key]
        if self.validators:
            init = None
            if self.init_defaults:
                init = {}
                for name, default_factory in self.init_defaults:
                    if name in values:
                        init[name] = values[name]
                    elif not field_errors or name not in field_errors:
                        assert default_factory is not None
                        init[name] = default_factory()
            aliases = values.keys()
            # Don't keep validators when all dependencies are default
            validators = [
                v for v in self.validators if not v.dependencies.isdisjoint(aliases)
            ]
            if field_errors or errors:
                error = ValidationError(errors or [], field_errors or {})
                invalid_fields = self.post_init_modified
                if field_errors:
                    invalid_fields |= field_errors.keys()
                try:
                    valid_validators = [
                        v
                        for v in validators
                        if v.dependencies.isdisjoint(invalid_fields)
                    ]
                    validate(
                        ValidatorMock(self.constructor.cls, values),
                        valid_validators,
                        init,
                        aliaser=self.aliaser,
                    )
                except ValidationError as err:
                    error = merge_errors(error, err)
                raise error
            obj = Constructor_construct(self.constructor, values)
            return validate(obj, validators, init, aliaser=self.aliaser)
        elif field_errors or errors:
            raise ValidationError(errors or [], field_errors or {})
        return Constructor_construct(self.constructor, values)

cdef inline NoneMethod_deserialize(NoneMethod self, object data):
        if data is not None:
            raise bad_type(data, NoneType)
        return data

cdef inline IntMethod_deserialize(IntMethod self, object data):
        if not isinstance(data, int):
            raise bad_type(data, int)
        return data

cdef inline ConstrainedIntMethod_deserialize(ConstrainedIntMethod self, object data):
        return validate_constraints(IntMethod_deserialize(<IntMethod>self, data), self.constraints, None)

cdef inline FloatMethod_deserialize(FloatMethod self, object data):
        if isinstance(data, float):
            return data
        elif isinstance(data, int):
            return float(data)
        else:
            raise bad_type(data, float)

cdef inline ConstrainedFloatMethod_deserialize(ConstrainedFloatMethod self, object data):
        return validate_constraints(FloatMethod_deserialize(<FloatMethod>self, data), self.constraints, None)

cdef inline StrMethod_deserialize(StrMethod self, object data):
        if not isinstance(data, str):
            raise bad_type(data, str)
        return data

cdef inline ConstrainedStrMethod_deserialize(ConstrainedStrMethod self, object data):
        return validate_constraints(StrMethod_deserialize(<StrMethod>self, data), self.constraints, None)

cdef inline BoolMethod_deserialize(BoolMethod self, object data):
        if not isinstance(data, bool):
            raise bad_type(data, bool)
        return data

cdef inline SubprimitiveMethod_deserialize(SubprimitiveMethod self, object data):
        return self.cls(DeserializationMethod_deserialize(self.method, data))

cdef inline TupleMethod_deserialize(TupleMethod self, object data):
        if not isinstance(data, list):
            raise bad_type(data, list)
        data_len = len(data)
        if data_len != len(self.elt_methods):
            if data_len < len(self.elt_methods):
                raise ValidationError(format_error(self.min_len_error, data))
            elif data_len > len(self.elt_methods):
                raise ValidationError(format_error(self.max_len_error, data))
            else:
                raise NotImplementedError
        elt_errors: dict = {}
        elts: list = [None] * len(self.elt_methods)
        for i in range(len(self.elt_methods)):
            elt_method: DeserializationMethod = self.elt_methods[i]
            try:
                elts[i] = DeserializationMethod_deserialize(elt_method, data[i])
            except ValidationError as err:
                elt_errors[i] = err
        validate_constraints(data, self.constraints, elt_errors)
        return tuple(elts)

cdef inline OptionalMethod_deserialize(OptionalMethod self, object data):
        if data is None:
            return None
        try:
            return DeserializationMethod_deserialize(self.value_method, data)
        except ValidationError as err:
            if self.coercer is not None and self.coercer(NoneType, data) is None:
                return None
            else:
                raise merge_errors(err, bad_type(data, NoneType))

cdef inline UnionByTypeMethod_deserialize(UnionByTypeMethod self, object data):
        try:
            method: DeserializationMethod = self.method_by_cls[type(data)]
            return DeserializationMethod_deserialize(method, data)
        except KeyError:
            raise bad_type(data, *self.method_by_cls) from None
        except ValidationError as err:
            other_classes = (cls for cls in self.method_by_cls if cls is not type(data))
            raise merge_errors(err, bad_type(data, *other_classes))

cdef inline UnionMethod_deserialize(UnionMethod self, object data):
        error = None
        for i in range(len(self.alt_methods)):
            alt_method: DeserializationMethod = self.alt_methods[i]
            try:
                return DeserializationMethod_deserialize(alt_method, data)
            except ValidationError as err:
                error = merge_errors(error, err)
        assert error is not None
        raise error

cdef inline ConversionMethod_deserialize(ConversionMethod self, object data):
        return self.converter(DeserializationMethod_deserialize(self.method, data))

cdef inline ConversionWithValueErrorMethod_deserialize(ConversionWithValueErrorMethod self, object data):
        value = DeserializationMethod_deserialize(self.method, data)
        try:
            return self.converter(value)
        except ValueError as err:
            raise ValidationError(str(err))

cdef inline ConversionUnionMethod_deserialize(ConversionUnionMethod self, object data):
        error: Optional[ValidationError] = None
        for i in range(len(self.alternatives)):
            alternative: ConversionAlternative = self.alternatives[i]
            try:
                value = DeserializationMethod_deserialize(alternative.method, data)
            except ValidationError as err:
                error = merge_errors(error, err)
                continue
            try:
                return alternative.converter(value)
            except ValidationError as err:
                error = merge_errors(error, err)
            except ValueError as err:
                if not alternative.value_error:
                    raise
                error = merge_errors(error, ValidationError(str(err)))
        assert error is not None
        raise error

cdef inline DiscriminatorMethod_deserialize(DiscriminatorMethod self, object data):
        if not isinstance(data, dict):
            raise bad_type(data, dict)
        if self.alias not in data:
            raise ValidationError([], {self.alias: ValidationError(self.missing)})
        try:
            method: DeserializationMethod = self.mapping[data[self.alias]]
        except (TypeError, KeyError):
            raise ValidationError(
                [],
                {
                    self.alias: ValidationError(
                        format_error(self.error, data[self.alias])
                    )
                },
            )
        else:
            return DeserializationMethod_deserialize(method, data)

cdef inline NoConstructor_construct(NoConstructor self, dict fields):
        return fields

cdef inline RawConstructor_construct(RawConstructor self, dict fields):
        return self.cls(**fields)

cdef inline FieldsConstructor_construct(FieldsConstructor self, dict fields):
        obj: object = object.__new__(self.cls)
        obj_dict: dict = obj.__dict__
        obj_dict.update(fields)
        if len(fields) != self.nb_fields:
            for i in range(len(self.default_fields)):
                default_field: DefaultField = self.default_fields[i]
                if default_field.name not in fields:
                    obj_dict[default_field.name] = default_field.default_value
            for i in range(len(self.factory_fields)):
                factory_field: FactoryField = self.factory_fields[i]
                if factory_field.name not in fields:
                    obj_dict[factory_field.name] = factory_field.factory()
        return obj

cdef inline Constraint_validate(Constraint self, object data):
    cdef int _dispatch = self._dispatch
    if _dispatch == 0:
        return MinimumConstraint_validate(<MinimumConstraint>self, data)
    elif _dispatch == 1:
        return MaximumConstraint_validate(<MaximumConstraint>self, data)
    elif _dispatch == 2:
        return ExclusiveMinimumConstraint_validate(<ExclusiveMinimumConstraint>self, data)
    elif _dispatch == 3:
        return ExclusiveMaximumConstraint_validate(<ExclusiveMaximumConstraint>self, data)
    elif _dispatch == 4:
        return MultipleOfConstraint_validate(<MultipleOfConstraint>self, data)
    elif _dispatch == 5:
        return MinLengthConstraint_validate(<MinLengthConstraint>self, data)
    elif _dispatch == 6:
        return MaxLengthConstraint_validate(<MaxLengthConstraint>self, data)
    elif _dispatch == 7:
        return PatternConstraint_validate(<PatternConstraint>self, data)
    elif _dispatch == 8:
        return MinItemsConstraint_validate(<MinItemsConstraint>self, data)
    elif _dispatch == 9:
        return MaxItemsConstraint_validate(<MaxItemsConstraint>self, data)
    elif _dispatch == 10:
        return UniqueItemsConstraint_validate(<UniqueItemsConstraint>self, data)
    elif _dispatch == 11:
        return MinPropertiesConstraint_validate(<MinPropertiesConstraint>self, data)
    elif _dispatch == 12:
        return MaxPropertiesConstraint_validate(<MaxPropertiesConstraint>self, data)

cdef inline DeserializationMethod_deserialize(DeserializationMethod self, object data):
    cdef int _dispatch = self._dispatch
    if _dispatch == 0:
        return RecMethod_deserialize(<RecMethod>self, data)
    elif _dispatch == 1:
        return ValidatorMethod_deserialize(<ValidatorMethod>self, data)
    elif _dispatch == 2:
        return CoercerMethod_deserialize(<CoercerMethod>self, data)
    elif _dispatch == 3:
        return TypeCheckMethod_deserialize(<TypeCheckMethod>self, data)
    elif _dispatch == 4:
        return AnyMethod_deserialize(<AnyMethod>self, data)
    elif _dispatch == 5:
        return ListCheckOnlyMethod_deserialize(<ListCheckOnlyMethod>self, data)
    elif _dispatch == 6:
        return ListMethod_deserialize(<ListMethod>self, data)
    elif _dispatch == 7:
        return SetMethod_deserialize(<SetMethod>self, data)
    elif _dispatch == 8:
        return FrozenSetMethod_deserialize(<FrozenSetMethod>self, data)
    elif _dispatch == 9:
        return VariadicTupleMethod_deserialize(<VariadicTupleMethod>self, data)
    elif _dispatch == 10:
        return LiteralMethod_deserialize(<LiteralMethod>self, data)
    elif _dispatch == 11:
        return MappingCheckOnly_deserialize(<MappingCheckOnly>self, data)
    elif _dispatch == 12:
        return MappingMethod_deserialize(<MappingMethod>self, data)
    elif _dispatch == 13:
        return SimpleObjectMethod_deserialize(<SimpleObjectMethod>self, data)
    elif _dispatch == 14:
        return ObjectMethod_deserialize(<ObjectMethod>self, data)
    elif _dispatch == 15:
        return NoneMethod_deserialize(<NoneMethod>self, data)
    elif _dispatch == 16:
        return IntMethod_deserialize(<IntMethod>self, data)
    elif _dispatch == 17:
        return ConstrainedIntMethod_deserialize(<ConstrainedIntMethod>self, data)
    elif _dispatch == 18:
        return FloatMethod_deserialize(<FloatMethod>self, data)
    elif _dispatch == 19:
        return ConstrainedFloatMethod_deserialize(<ConstrainedFloatMethod>self, data)
    elif _dispatch == 20:
        return StrMethod_deserialize(<StrMethod>self, data)
    elif _dispatch == 21:
        return ConstrainedStrMethod_deserialize(<ConstrainedStrMethod>self, data)
    elif _dispatch == 22:
        return BoolMethod_deserialize(<BoolMethod>self, data)
    elif _dispatch == 23:
        return SubprimitiveMethod_deserialize(<SubprimitiveMethod>self, data)
    elif _dispatch == 24:
        return TupleMethod_deserialize(<TupleMethod>self, data)
    elif _dispatch == 25:
        return OptionalMethod_deserialize(<OptionalMethod>self, data)
    elif _dispatch == 26:
        return UnionByTypeMethod_deserialize(<UnionByTypeMethod>self, data)
    elif _dispatch == 27:
        return UnionMethod_deserialize(<UnionMethod>self, data)
    elif _dispatch == 28:
        return ConversionMethod_deserialize(<ConversionMethod>self, data)
    elif _dispatch == 29:
        return ConversionWithValueErrorMethod_deserialize(<ConversionWithValueErrorMethod>self, data)
    elif _dispatch == 30:
        return ConversionUnionMethod_deserialize(<ConversionUnionMethod>self, data)
    elif _dispatch == 31:
        return DiscriminatorMethod_deserialize(<DiscriminatorMethod>self, data)

cdef inline Constructor_construct(Constructor self, dict fields):
    cdef int _dispatch = self._dispatch
    if _dispatch == 0:
        return NoConstructor_construct(<NoConstructor>self, fields)
    elif _dispatch == 1:
        return RawConstructor_construct(<RawConstructor>self, fields)
    elif _dispatch == 2:
        return FieldsConstructor_construct(<FieldsConstructor>self, fields)


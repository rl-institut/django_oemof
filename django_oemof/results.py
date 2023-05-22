"""Module to calculate oemof results"""

import inspect
from typing import Union, Type, Dict
import pandas

from oemof.tabular.postprocessing import core, calculations as standard_calculations

from . import simulation, models


CALCULATIONS: Dict[str, Union[Type[core.Calculation], core.ParametrizedCalculation]] = {
    core.get_dependency_name(member): member
    for (name, member) in inspect.getmembers(standard_calculations)
    if inspect.isclass(member) and not inspect.isabstract(member) and issubclass(member, core.Calculation)
}


def register_calculation(*calculations: Union[Type[core.Calculation], core.ParametrizedCalculation]):
    """
    Custom calculations have to be registered first, in order to use them via API
    """
    for calculation in calculations:
        CALCULATIONS[core.get_dependency_name(calculation)] = calculation


def get_results(
    simulation_id: int,
    calculations: list[Union[str, Type[core.Calculation], core.ParametrizedCalculation]],
) -> dict[str, Union[pandas.Series, pandas.DataFrame]]:
    """
    Tries to load results from database.
    If result is not found, simulation data is loaded from db or simulated (if not in DB yet)
    and results are calculated.

    Parameters
    ----------
    simulation_id : int
        ID if simulation
    calculations : list[Union[str, Type[core.Calculation], core.ParametrizedCalculation]]
        List of calculations (by name or class) which shall be calculated

    Returns
    -------
    dict
        Dict containing calculation name as key and calculation result as value
    """
    try:
        sim = models.Simulation.objects.get(pk=simulation_id)  # pylint: disable=E1101
    except models.Simulation.DoesNotExist:  # pylint: disable=E1101
        # pylint: disable=W0707
        raise simulation.SimulationError(f"Simulation with ID#{simulation_id} not present in database.")

    results = {}
    for calculation in calculations:
        calculation_name = calculation if isinstance(calculation, str) else core.get_dependency_name(calculation)
        try:
            calculation_result = sim.results.get(name=calculation_name)
        except models.Result.DoesNotExist:  # pylint: disable=E1101
            continue
        result = pandas.read_json(calculation_result.data, orient="table")
        results[calculation_name] = result["values"] if calculation_result.data_type == "series" else result

    if len(results) != len(calculations):
        calculator = core.Calculator(*sim.dataset.restore_results())
        for calculation in calculations:
            calculation_name = calculation if isinstance(calculation, str) else core.get_dependency_name(calculation)
            if calculation_name in results:
                continue
            calculation_cls = CALCULATIONS[calculation] if isinstance(calculation, str) else calculation
            if isinstance(calculation_cls, core.ParametrizedCalculation):
                parameters = calculation_cls.parameters or {}
                result = calculation_cls.calculation(calculator, **parameters).result
            else:
                result = calculation_cls(calculator).result
            models.Result(
                simulation=sim,
                name=calculation_name,
                data=result.to_json(orient="table"),
                data_type="series" if isinstance(result, pandas.Series) else "frame",
            ).save()
            results[calculation_name] = result
    return results

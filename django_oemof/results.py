import inspect
from typing import Union
import pandas

from . import simulation, models

from oemoflex.postprocessing import core, postprocessing


CALCULATIONS = {
    member.name: member
    for (name, member) in inspect.getmembers(postprocessing)
    if inspect.isclass(member) and not inspect.isabstract(member) and issubclass(member, core.Calculation)
}


def register_calculation(*calculations: core.Calculation):
    """
    Custom calculations have to be registered first, in order to use them via API
    """
    for calculation in calculations:
        CALCULATIONS[calculation.name] = calculation


def get_results(
    scenario: str, parameters: dict, calculations: list[str]
) -> dict[str, Union[pandas.Series, pandas.DataFrame]]:
    """
    Tries to load results from database.
    If result is not found, simulation data is loaded from db or simulated (if not in DB yet)
    and results are calculated.

    Parameters
    ----------
    scenario : dict
        Scenario name
    parameters : dict
        Adapted parameters
    calculations : list[str]
        List of calculations (by name) which shall be calculated

    Returns
    -------
    dict
        Dict containing calculation name as key and calculation result as value
    """
    try:
        sim = models.Simulation.objects.get(scenario=scenario, parameters=parameters)
    except models.Simulation.DoesNotExist:
        raise simulation.SimulationError(f"Simulation for {scenario=} with {parameters=} not present in database.")

    results = {}
    for calculation in calculations:
        try:
            calculation_instance = sim.results.get(name=calculation)
        except models.Result.DoesNotExist:
            continue
        result = pandas.read_json(calculation_instance.data, orient="table")
        results[calculation] = result["values"] if calculation_instance.data_type == "series" else result

    if any(calculation not in results for calculation in calculations):
        input_data, output_data = simulation.simulate_scenario(scenario, parameters)
        sim = models.Simulation.objects.get(scenario=scenario, parameters=parameters)
        calculator = postprocessing.Calculator(input_data, output_data)
        for calculation in calculations:
            if calculation in results:
                continue
            result = CALCULATIONS[calculation](calculator).result
            models.Result(
                simulation=sim,
                name=calculation,
                data=result.to_json(orient="table"),
                data_type="series" if isinstance(result, pandas.Series) else "frame",
            ).save()
            results[calculation] = result
    return results

import os
import inspect
import types
import re
import hashlib
import numpy as np
import tables as tb
import explanes.util as eu
import copy
from itertools import compress

class Metric():
  """Stores information about the way evaluation metrics are stored and manipulated.

  Stores information about the way evaluation metrics are stored and manipulated. Each member of this class describes an evaluation metric and the way it may be abstracted. Two NameSpaces (explanes.metric.Metric._unit, explanes.metric.Metric._description) are available to respectively provide information about the unit of the metric and its semantic.

  Each metric may be reduced by any mathematical operation that operate on a vector made available by the numpy library with default parameters.

  Two pruning strategies can be complemented to this description in order to remove some items of the metric vector before being abstracted.

  One can select one value of the vector by providing its index.

  Examples
  --------

  >>> import explanes as el
  >>> m = el.metric.Metric()
  >>> m.duration = ['mean', 'std']
  >>> m._unit.duration = 'second'
  >>> m._description = 'duration of the processing'

  It is sometimes useful to store complementary data useful for plotting that must not be considered during the reduction.

  >>> m.metric1 = ['median-0', 'min-0', 'max-0']

  In this case, the first value will be removed before reduction.

  >>> m.metric2 = ['median-2', 'min-2', 'max-2', '0%']

  In this case, the odd values will be removed before reduction and the last reduction will select the first value of the metric vector, expressed in percents by multiplying it by 100.
  """

  _unit = types.SimpleNamespace()
  _description = types.SimpleNamespace()
  _metrics = []

  def __setattr__(
    self,
    name,
    value
    ):
    if not hasattr(self, name) and name[0] != '_':
      self._metrics.append(name)
    return object.__setattr__(self, name, value)

  def reduceFromNpy(
    self,
    settings,
    dataLocation,
    settingEncoding={},
    verbose = False
    ):
    """Handle reduction of the metrics when considering numpy storage.

    The method handles the reduction of the metrics when considering numpy storage. For each metric, a .npy file is assumed to be available which the following naming convention: <id_of_setting>_<metricName>.npy.

    The method :meth:`explanes.metric.Metric.reduce` wraps this method and should be considered as the main user interface, please see its documentation for usage.

    See Also
    --------

    explanes.metric.Metric.reduce

    """
    table = []
    metricHasData = [False] * len(self.name())
    nbReducedMetrics = 0
    for mIndex, metric in enumerate(self.name()):
      for reductionType in self.__getattribute__(metric):
        nbReducedMetrics += 1
    reducedMetrics = [False] * nbReducedMetrics
    for sIndex, setting in enumerate(settings):
      row = []
      idx = 0
      for mIndex, metric in enumerate(self.name()):
        fileName = dataLocation+setting.id(**settingEncoding)+'_'+metric+'.npy'
        if os.path.exists(fileName):
          if verbose:
            print('Found '+fileName)
          metricHasData[mIndex] = True
          data = np.load(fileName)
          for reductionType in self.__getattribute__(metric):
            reducedMetrics[idx] = True
            idx+=1
            row.append(self.reduceMetric(data, reductionType))
        else:
          if verbose:
            print('** Unable to find '+fileName)
          for reductionType in self.__getattribute__(metric):
            row.append(np.nan)
            idx+=1
      if len(row):
        for factorName in reversed(settings.getFactorNames()):
          row.insert(0, setting.__getattribute__(factorName))
        table.append(row)
    nbFactors = len(settings.getFactorNames())
    for ir, row in enumerate(table):
      table[ir] = row[:nbFactors]+list(compress(row[nbFactors:], reducedMetrics))
    return (table, metricHasData)

  def reduceFromH5(
    self,
    settings,
    dataLocation,
    settingEncoding={},
    verbose = False
    ):
    """Handle reduction of the metrics when considering numpy storage.

    The method handles the reduction of the metrics when considering h5 storage.

    The method :meth:`explanes.metric.Metric.reduce` wraps this method and should be considered as the main user interface, please see its documentation for usage.

    See Also
    --------

    explanes.metric.Metric.reduce

    """
    table = []
    h5 = tb.open_file(dataLocation, mode='r')
    metricHasData = [False] * len(self.name())
    for sIndex, setting in enumerate(settings):
      row = []
      if verbose:
        print('Seeking Group '+setting.id(**settingEncoding))
      if h5.root.__contains__(setting.id(**settingEncoding)):
        sg = h5.root._f_get_child(setting.id(**settingEncoding))
        # print(sg._v_name)
        # print(setting.id(**settingEncoding))
        for mIndex, metric in enumerate(self.name()):
          for reductionType in self.__getattribute__(metric):
            value = np.nan
            if sg.__contains__(metric):
              metricHasData[mIndex] = True
              data = sg._f_get_child(metric)
            row.append(self.reduceMetric(data, reductionType))
        if len(row):
          for factorName in reversed(settings.getFactorNames()):
            row.insert(0, setting.__getattribute__(factorName))
        table.append(row)
    h5.close()
    return (table, metricHasData)

  def reduceMetric(
    self,
    data,
    reductionType
    ):
    """Apply reduction directive to a metric vector after potentially remove non wanted items from the vector.

    The data vector is reduced by considering the reduction directive after potentially remove non wanted items from the vector.

    Parameters
    ----------

    data : numpy array
      1-D vector to be reduced.

    reductionType : str
      type of reduction to be applied to the data vector. Can be any numpy method that can applied to a vector and returns a value. Selectors and layout can also be specified.

    Examples
    --------

    >>> import explanes as el
    >>> import numpy as np
    >>> data = np.linspace(1, 10, num=10)
    [ 1.  2.  3.  4.  5.  6.  7.  8.  9. 10.]
    >>> m  =el.metric.Metric()
    >>> m.reduceMetric(data, 0)
    1.0
    >>> m.reduceMetric(data, 8)
    9.0
    >>> m.reduceMetric(data, 'sum%')
    5500.0
    >>> m.reduceMetric(data, 'sum-0')
    54.0
    >>> m.reduceMetric(data, 'sum-1')
    25.0
    >>> m.reduceMetric(data, 'sum-2')
    30.0

    """
    indexPercent=-1
    if reductionType:
      if isinstance(reductionType, int):
        if data.size>1:
          value = float(data[reductionType])
        else:
          value = float(data)
      elif isinstance(reductionType, str):
        indexPercent = reductionType.find('%')
        if indexPercent>-1:
          reductionType = reductionType.replace('%', '')
        ags = reductionType.split('-')
        reductionType = ags[0]
        if len(ags)>1:
          ignore = int(ags[1])
          if ignore == 0:
            value = getattr(np, reductionType)(data[1:])
          elif ignore == 1:
            value = getattr(np, reductionType)(data[::2])
          elif ignore == 2:
            value = getattr(np, reductionType)(data[1::2])
          else:
            print('Unrecognized pruning directive')
            raise ValueError
        else :
          value = getattr(np, reductionType)(data)
    else:
      data = np.array(data)
      if data.size>1:
        value = float(data[0])
      else:
        value = float(data)
    if indexPercent>-1:
      value *= 100
    return value

  def reduce(
    self,
    settings,
    dataLocation,
    settingEncoding={},
    factorDisplay='long',
    factorDisplayLength=2,
    reducedMetricDisplay = 'capitalize',
    verbose = False
    ):
    """Apply the reduction directives described in each members of explanes.metric.Metric objects for the settings given as parameters.

    For each setting in the iterable settings, available data corresponding to the metrics specified as members of the explanes.metric.Metric object are reduced using specified reduction methods.

    Parameters
    ----------

    settings: explanes.factor.Factor
      iterable settings.

    dataLocation: str
      In the case of .npy storage, a valid path to the main directory. In the case of .h5 storage, a valid path to an .h5 file.

    settingEncoding : dict
      Encoding of the setting. See explanes.factor.Factor.id for references.


    reducedMetricDisplay : str (optional)
      If set to 'capitalize' (default), the description of the reduced metric is done in a Camel case fashion: metricReduction.

      If set to 'underscore', the description of the reduced metric is done in a Python case fashion: metric_reduction.

    factor : explanes.factor.Factor
      The explanes.factor.Factor describing the factors of the experiment.

    factorDisplay : str (optional)
      The expected format of the display of factors. 'long' (default) do not lead to any reduction. If factorDisplay contains 'short', a reduction of each word is performed. 'shortUnderscore' assumes pythonCase delimitation. 'shortCapital' assumes camelCase delimitation. 'short' attempts to perform reduction by guessing the type of delimitation.

    factorDisplayLength : int (optional)
      If factorDisplay has 'short', factorDisplayLength specifies the maximal length of each word of the description of the factor.

    reducedMetricDisplay : str (optional)
      If set to 'capitalize' (default), the description of the reduced metric is done in a Camel case fashion: metricReduction.

      If set to 'underscore', the description of the reduced

    verbose : bool
      In the case of .npy metric storage, if verbose is set to True, print the fileName seeked for each metric.

      In the case of .h5 metric storage, if verbose is set to True, print the group seeked for each metric.

    Returns
    -------

    settingDescription : list of lists of literals
      A settingDescription, stored as a list of list of literals of the same size. The main list stores the rows of the settingDescription.

    columnHeader : list of str
      The column header of the settingDescription as a list of str, describing the factors (left side), and the reduced metrics (right side).

    constantSettingDescription : str
      When a factor is equally valued for all the settings, the factor column is removed from the settingDescription and stored in constantSettingDescription along its value.

    nbColumnFactor : int
      The number of factors in the column header.

    Examples
    --------

    explanes supports metrics storage using an .npy file per metric per setting.

    >>> import explanes as el
    >>> import numpy as np
    >>> import pandas as pd
    >>> experiment = el.experiment.Experiment()
    >>> experiment.project.name = 'example'
    >>> experiment.path.output = '/tmp/'+experiment.project.name+'/'
    >>> experiment.factor.f1 = [1, 2]
    >>> experiment.factor.f2 = [1, 2, 3]
    >>> experiment.metric.m1 = ['mean', 'std']
    >>> experiment.metric.m2 = ['min', 'argmin']
    >>> def process(setting, experiment):
    >>>   metric1 = setting.f1+setting.f2+np.random.randn(100)
    >>>   metric2 = setting.f1*setting.f2*np.random.randn(100)
    >>>   np.save(experiment.path.output+setting.id()+'_m1.npy', metric1)
    >>>   np.save(experiment.path.output+setting.id()+'_m2.npy', metric2)
    >>> experiment.makePaths()
    >>> experiment.do([], process, progress=False)
    >>> (settingDescription, columns, header) = experiment.metric.reduce(experiment.factor.settings(), experiment.path.output)

    >>> df = pd.DataFrame(settingDescription, columns=columns).round(decimals=2)
    f1  f2  m1Mean  m1Std  m2Min  m2Argmin
    0   1   1    1.83   0.99  -2.38        83
    1   1   2    3.04   1.01  -5.01        57
    2   1   3    3.94   0.92  -5.96        12
    3   2   1    2.93   1.07  -6.47        71
    4   2   2    3.84   1.03 -11.47        32
    5   2   3    4.88   1.02 -11.61        90

    explanes also supports metrics storage using one .h5 file sink structured with settings as groups et metrics as leaf nodes.

    >>> import explanes as el
    >>> import numpy as np
    >>> import tables as tb
    >>> import pandas as pd
    >>> experiment = el.experiment.Experiment()
    >>> experiment.project.name = 'example'
    >>> experiment.path.output = '/tmp/'+experiment.project.name+'.h5'
    >>> experiment.factor.f1 = [1, 2]
    >>> experiment.factor.f2 = [1, 2, 3]
    >>> experiment.metric.m1 = ['mean', 'std']
    >>> experiment.metric.m2 = ['min', 'argmin']
    >>> def process(setting, experiment):
    >>>   h5 = tb.open_file(experiment.path.output, mode='a')
    >>>   sg = experiment.metric.h5addSetting(h5, setting,
    >>>       metricDimensions = [100, 100])
    >>>   sg.m1[:] = setting.f1+setting.f2+np.random.randn(100)
    >>>   sg.m2[:] = setting.f1*setting.f2*np.random.randn(100)
    >>>   h5.close()
    >>> experiment.makePaths()
    >>> experiment.do([], process, progress=False)
    >>> h5 = tb.open_file(experiment.path.output, mode='r')
    /tmp/example.h5 (File) ''
    Last modif.: 'Thu Sep 24 17:03:45 2020'
    Object Tree:
    / (RootGroup) ''
    /f1_1_f2_1 (Group) 'f1 1 f2 1'
    /f1_1_f2_1/m1 (Array(100,)) 'm1'
    /f1_1_f2_1/m2 (Array(100,)) 'm2'
    /f1_1_f2_2 (Group) 'f1 1 f2 2'
    /f1_1_f2_2/m1 (Array(100,)) 'm1'
    /f1_1_f2_2/m2 (Array(100,)) 'm2'
    /f1_1_f2_3 (Group) 'f1 1 f2 3'
    /f1_1_f2_3/m1 (Array(100,)) 'm1'
    /f1_1_f2_3/m2 (Array(100,)) 'm2'
    /f1_2_f2_1 (Group) 'f1 2 f2 1'
    /f1_2_f2_1/m1 (Array(100,)) 'm1'
    /f1_2_f2_1/m2 (Array(100,)) 'm2'
    /f1_2_f2_2 (Group) 'f1 2 f2 2'
    /f1_2_f2_2/m1 (Array(100,)) 'm1'
    /f1_2_f2_2/m2 (Array(100,)) 'm2'
    /f1_2_f2_3 (Group) 'f1 2 f2 3'
    /f1_2_f2_3/m1 (Array(100,)) 'm1'
    /f1_2_f2_3/m2 (Array(100,)) 'm2'
    >>> h5.close()
    >>> (settingDescription, columns, header) = experiment.metric.reduce(experiment.factor.settings(), experiment.path.output)

    >>> df = pd.DataFrame(settingDescription, columns=columns).round(decimals=2)
    >>> print(df)
    f1  f2  m1Mean  m1Std  m2Min  m2Argmin
    0   1   1    1.89   0.94  -2.42        11
    1   1   2    3.03   1.10  -5.08        29
    2   1   3    3.84   0.94  -6.27        99
    3   2   1    2.93   0.89  -4.91        18
    4   2   2    3.99   1.01 -13.51        70
    5   2   3    5.08   0.86 -13.36        87
    """
    if dataLocation.endswith('.h5'):
      (settingDescription, metricHasData) = self.reduceFromH5(settings, dataLocation, settingEncoding, verbose)
    else:
      (settingDescription, metricHasData) = self.reduceFromNpy(settings, dataLocation, settingEncoding, verbose)

    columnHeader = self.getColumnHeader(settings, factorDisplay, factorDisplayLength, metricHasData, reducedMetricDisplay)

    # constantSettingDescription = ''
    nbColumnFactor = len(settings.getFactorNames())
    # if len(settingDescription)>1:
    #   (ccIndex, ccValue) = eu.constantColumn(settingDescription)
    #   ccIndex = [i for i, x in enumerate(ccIndex) if x and i<nbColumnFactor]
    #   nbColumnFactor -= len(ccIndex)
    #   for s in ccIndex:
    #     constantSettingDescription += eu.compressDescription(columnHeader[s], factorDisplay)+': '+str(ccValue[s])+' '
    #   for s in sorted(ccIndex, reverse=True):
    #     columnHeader.pop(s)
    #     for r in settingDescription:
    #       r.pop(s)
    return eu.pruneSettingDescription(settingDescription, columnHeader, nbColumnFactor, factorDisplay)

  def get(
    self,
    metric,
    settings,
    dataLocation,
    settingEncoding={},
    verbose=False
    ):
    """ Get the metric vector from an .npy or a group of a .h5 file.

    Get the metric vector as a numpy array from an .npy or a group of a .h5 file.

    Parameters
    ----------

    metric: str
      The name of the metric. Must be a member of the explanes.metric.Metric object.

    settings: explanes.factor.Factor
      Iterable settings.

    dataLocation: str
      In the case of .npy storage, a valid path to the main directory. In the case of .h5 storage, a valid path to an .h5 file.

    settingEncoding : dict
      Encoding of the setting. See explanes.factor.Factor.id for references.

    verbose : bool
      In the case of .npy metric storage, if verbose is set to True, print the fileName seeked for the metric.

      In the case of .h5 metric storage, if verbose is set to True, print the group seeked for the metric.

    Returns
    -------

    Examples
    --------

    """

    settingMetric = []
    settingDescription = []
    settingDescriptionFormat = copy.deepcopy(settingEncoding)
    settingDescriptionFormat['format'] = 'list'
    settingDescriptionFormat['hideNonAndZero'] = False
    settingDescriptionFormat['hideDefault'] = False

    if isinstance(dataLocation, str):
      if dataLocation.endswith('.h5'):
        h5 = tb.open_file(dataLocation, mode='r')
        for setting in settings:
          if h5.root.__contains__(setting.id(**settingEncoding)):
            if verbose:
              print('Found group '+setting.id(**settingEncoding))
            sg = h5.root._f_get_child(setting.id(**settingEncoding))
            if sg.__contains__(metric):
              settingMetric.append(np.array(sg._f_get_child(metric)))
              settingDescription.append(setting.id(**settingDescriptionFormat))
          elif verbose:
            print('** Unable to find group '+setting.id(**settingEncoding))
        h5.close()
      else:
        for setting in settings:
          fileName = dataLocation+setting.id(**settingEncoding)+'_'+metric+'.npy'
          if os.path.exists(fileName):
            if verbose:
              print('Found '+fileName)
            settingMetric.append(np.load(fileName))
            settingDescription.append(setting.id(**settingDescriptionFormat))
          elif verbose:
            print('** Unable to find '+fileName)

    (settingDescription, columnHeader, constantSettingDescription, nbColumnFactor) = eu.pruneSettingDescription(settingDescription)

    return (settingMetric, settingDescription, constantSettingDescription)


  # def getFromH5(
  #   self,
  #   metric,
  #   settings,
  #   dataLocation,
  #   settingEncoding={},
  #   verbose=False
  #   ):
  #   """one liner
  #
  #   Desc
  #
  #   Examples
  #   --------
  #
  #   """
  #   h5 = tb.open_file(dataLocation, mode='r')
  #   data = []
  #   settingDescription = []
  #   settingDescriptionFormat = copy.deepcopy(kwargs)
  #   settingDescriptionFormat['format'] = 'list'
  #   settingDescriptionFormat['hideNonAndZero'] = False
  #   settingDescriptionFormat['hideDefault'] = False
  #   for setting in settings:
  #     if verbose:
  #       print('Seeking Group '+setting.id(**settingEncoding))
  #     if h5.root.__contains__(setting.id(**settingEncoding)):
  #       sg = h5.root._f_get_child(setting.id(**settingEncoding))
  #       if sg.__contains__(metric):
  #         data.append(sg._f_get_child(metric))
  #         settingDescription.append(setting.id(**settingDescriptionFormat))
  #   h5.close()
  #   return (data, settingDescription)
  #
  # def getFromNpy(
  #   self,
  #   metric,
  #   settings,
  #   dataLocation,
  #   settingEncoding={},
  #   verbose=False
  #   ):
  #   """one liner
  #
  #   Desc
  #
  #   Examples
  #   --------
  #
  #   """
  #   data = []
  #   settingDescription = []
  #   settingDescriptionFormat = copy.deepcopy(settingEncoding)
  #   settingDescriptionFormat['format'] = 'list'
  #   settingDescriptionFormat['hideNonAndZero'] = False
  #   settingDescriptionFormat['hideDefault'] = False
  #   for setting in settings:
  #     fileName = dataLocation+setting.id(**settingEncoding)+'_'+metric+'.npy'
  #     if os.path.exists(fileName):
  #       data.append(np.load(fileName))
  #       settingDescription.append(setting.id(**settingDescriptionFormat))
  #
  #   return (data, settingDescription)

  def h5addSetting(
    self,
    h5fid,
    setting,
    metricDimensions=[],
    settingEncoding={}
    ):
    """one liner

    Desc

    Parameters
    ----------

    h5fid,
    setting,
    metricDimensions=[],
    settingEncoding={}


    Examples
    --------

    """
    groupName = setting.id(**settingEncoding)
    # print(groupName)
    if not h5fid.__contains__('/'+groupName):
      sg = h5fid.create_group('/', groupName, setting.id(settingEncoding))
    else:
      sg = h5fid.root._f_get_child(groupName)
    for mIndex, metric in enumerate(self.name()):
      if hasattr(self._description, metric):
        description = getattr(self._description, metric)
      else:
        description = metric

      if hasattr(self._unit, metric):
        description += ' in ' + getattr(self._unit, metric)

      if not metricDimensions:
        if sg.__contains__(metric):
          sg._f_get_child(metric)._f_remove()
        h5fid.create_earray(sg, metric, tb.Float64Atom(), (0,), description)
      else:
        if not sg.__contains__(metric):
          h5fid.create_array(sg, metric, np.zeros(( metricDimensions[mIndex])), description)
    return sg

  def getColumnHeader(
    self,
    factor,
    factorDisplay='long',
    factorDisplayLength=2,
    metricHasData=[],
    reducedMetricDisplay = 'capitalize',
    ):
    """Builds the column header of the reduction settingDescription.

    This method builds the column header of the reduction settingDescription by formating the Factor names from the explanes.factor.Factor class and by describing the reduced metrics.

    Parameters
    ----------

    factor : explanes.factor.Factor
      The explanes.factor.Factor describing the factors of the experiment.

    factorDisplay : str (optional)
      The expected format of the display of factors. 'long' (default) do not lead to any reduction. If factorDisplay contains 'short', a reduction of each word is performed. 'shortUnderscore' assumes pythonCase delimitation. 'shortCapital' assumes camelCase delimitation. 'short' attempts to perform reduction by guessing the type of delimitation.

    factorDisplayLength : int (optional)
      If factorDisplay has 'short', factorDisplayLength specifies the maximal length of each word of the description of the factor.

    metricHasData : list of bool
      Specify for each metric described in the explanes.metric.Metric object, whether data has been loaded or not.

    reducedMetricDisplay : str (optional)
      If set to 'capitalize' (default), the description of the reduced metric is done in a Camel case fashion: metricReduction.

      If set to 'underscore', the description of the reduced metric is done in a Python case fashion: metric_reduction.

    See Also
    --------

    explanes.util.compressDescription
    """
    # print(factorDisplay)
    columnHeader = []
    for factorName in factor.getFactorNames():
      columnHeader.append(eu.compressDescription(factorName, factorDisplay, factorDisplayLength))
    for mIndex, metric in enumerate(self.name()):
      if metricHasData[mIndex]:
        for reductionType in self.__getattribute__(metric):
          if reducedMetricDisplay == 'capitalize':
            name = metric+str(reductionType).capitalize()
          elif reducedMetricDisplay == 'underscore':
            name = metric+'_'+reductionType
          else:
            print('Unrecognized reducedMetricDisplay value. Should be \'capitalize\' or \'underscore\'. Got:'+reducedMetricDisplay)
            raise ValueError
          columnHeader.append(name)
    return columnHeader

  def name(
    self
    ):
    """Returns a list of str with the names of the metrics.

    Returns a list of str with the names of the metricsdefined as members of the explanes.metric.Metric object.

    Examples
    --------

    >>> import explanes as el
    >>> m = el.metric.Metric()
    >>> m.duration = ['mean']
    >>> m.mse = ['mean']
    >>> m.name()
    ['duration', 'mse']
    """
    return self._metrics

  def __len__(
    self
    ):
    """Returns the number of metrics.

    Returns the number of metrics defined as members of the explanes.metric.Metric object.

    Examples
    --------

    >>> import explanes as el
    >>> m = el.metric.Metric()
    >>> m.duration = ['mean']
    >>> m.mse = ['mean']
    >>> len(m)
    2
    """
    return len(self.name())

  def __str__(
    self
    ):
    """Returns a str describing the explanes.metric.Metric.

    Returns a str describing the explanes.metric.Metric by listing each member of the object.

    Examples
    --------

    >>> import explanes as el
    >>> import numpy as np
    >>> m = el.metric.Metric()
    >>> m.duration = ['mean']
    >>> m._unit.duration = 'seconds'
    >>> m._description.duration = 'duration of the trial'
    >>> m.mse = ['mean']
    >>> m._unit.mse = ''
    >>> m._description.mse = 'Mean Square Error'
    >>> print(m)

    """
    cString = ''
    atrs = dict(vars(type(self)))
    atrs.update(vars(self))
    atrs = [a for a in atrs if a[0] !=  '_']

    for atr in atrs:
      if type(inspect.getattr_static(self, atr)) != types.FunctionType:
        cString+='  '+atr+': '+str(self.__getattribute__(atr))
        if hasattr(self._description, atr):
          cString+=', the '+str(self._description.__getattribute__(atr))+''
        if hasattr(self._unit, atr) and self._unit.__getattribute__(atr):
          cString+=' in '+str(self._unit.__getattribute__(atr))
        cString += '.\r\n'
    return cString

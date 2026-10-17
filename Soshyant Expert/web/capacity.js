'use strict';
let capacityCatalog, capacityResult, capacityLoading;
function capacityModels() {
  const selected = $('capacityModel').value;
  $('capacityModel').replaceChildren(...capacityCatalog.models.map(model => {
    const option = element('option', '', model.name + ' · ' + t(model.bundled ? 'Installed locally' : 'Planning profile only'));
    option.value = model.id;
    return option;
  }));
  if (selected) $('capacityModel').value = selected;
  capacityQuantizations();
}
function capacityQuantizations() {
  const previous = $('capacityQuant').value;
  const model = capacityCatalog.models.find(item => item.id === $('capacityModel').value);
  $('capacityQuant').replaceChildren(...Object.keys(model.weights_bytes).map(format => {
    const option = element('option', '', format); option.value = format; return option;
  }));
  if (previous in model.weights_bytes) $('capacityQuant').value = previous;
}
window.initializeCapacity = async function () {
  if (capacityCatalog || capacityLoading) return;
  capacityLoading = true;
  try {
    capacityCatalog = await api('/api/capacity/catalog');
    capacityModels();
    await calculateCapacity();
  } catch (error) {$('capacityError').textContent = error.message;}
  finally {capacityLoading = false;}
};
async function calculateCapacity() {
  if (!$('capacityForm').reportValidity()) return;
  $('calculateCapacity').disabled = true;
  $('capacityError').textContent = '';
  const data = {};
  for (const [key, id] of Object.entries({model_id:'Model',quantization:'Quant',users:'Users',activity_percent:'Activity',context_tokens:'Context',gpu_gib:'Gpu',target_tps:'Target',answer_tokens:'Output',headroom_percent:'Headroom',knowledge_ram_gib:'IndexRam',benchmark_tps:'Benchmark'})) data[key] = $('capacity' + id).value;
  try {
    capacityResult = await api('/api/capacity/estimate', {method:'POST', data});
    renderCapacity();
  } catch (error) {$('capacityError').textContent = error.message;}
  finally {$('calculateCapacity').disabled = false;}
}
function renderCapacity() {
  if (!capacityResult) return;
  const r = capacityResult, host = $('capacityResults');
  host.replaceChildren();
  const card = element('div', 'card capacity-summary');
  card.append(element('span','eyebrow',t(r.throughput_gpu_count ? 'PLAN WITH YOUR BENCHMARK' : 'MEMORY CAPACITY ESTIMATE')),
    element('h3','',r.model_name + ' · ' + r.quantization));
  if (r.planned_gpu_count) {
    card.append(element('div','capacity-hero',r.planned_gpu_count + ' × ' + r.gpu_class_gib + ' GiB'), element('p','',t('GPU memory per card')));
    const stats = element('div','capacity-stats');
    for (const [value,label] of [[r.ram_gib+' GiB','Host RAM'],[r.cpu_physical_cores,'Physical CPU cores'],[r.active_generations,'Simultaneous generations']]) {
      const item = element('div'); item.append(element('strong','',String(value)),element('small','',t(label))); stats.append(item);
    }
    card.append(stats,element('p','capacity-advisory',t('CPU and RAM are planning allowances for GPU inference, not measured hardware requirements. Use a modern AVX2-capable CPU.')));
  } else {
    card.append(element('h2','error',t('This model does not fit on the selected GPU.')),
      element('p','',t('Minimum memory class per GPU') + ': ' + (r.minimum_single_gpu_class_gib || '>' + r.gpu_class_gib) + ' GiB'));
  }
  const warning = element('div','capacity-warning',t('Memory fit does not guarantee response speed. Validate the chosen hardware with a representative load test.'));
  card.append(warning);
  host.append(card);
  const detail = element('div','card capacity-breakdown');
  detail.append(element('h3','',t('What drives the estimate')));
  const list = element('dl');
  for (const [label,value] of [
    ['Model weights',r.weights_gib+' GiB'],['KV cache per answer',r.kv_gib_per_sequence+' GiB'],
    ['Recurrent state reserve per answer',r.recurrent_gib_per_sequence+' GiB'],['Runtime reserve per GPU',r.runtime_reserve_gib_per_gpu+' GiB'],
    ['Memory headroom (%)',r.inputs.headroom_percent],['Estimated use per GPU',r.estimated_used_vram_per_gpu_gib === null ? '—' : r.estimated_used_vram_per_gpu_gib+' GiB'],
    ['Required aggregate tokens/sec',r.required_aggregate_tokens_per_second],['Target decode time (seconds)',r.target_decode_seconds]]) {
    list.append(element('dt','',t(label)),element('dd','',String(value)));
  }
  detail.append(list,element('p','',t(r.throughput_gpu_count ? 'GPU count also includes your supplied throughput measurement. Recheck performance at the planned concurrency.' : 'No throughput benchmark supplied: GPU count covers memory only. Target decode time is a goal, excluding queueing and prompt processing.')));
  host.append(detail,element('div','capacity-warning',t('Planning does not change deployment. This installation currently generates one answer at a time with a waiting queue; parallel replicas require deployment changes.')));
  $('capacityComparison').hidden = false;
  $('capacityRows').replaceChildren(...r.comparison.map(row => {
    const tr = element('tr',row.model_id === r.model_id ? 'selected' : '');
    const modelCell = element('td');
    modelCell.append(button(row.model_name,async()=>{
      $('capacityModel').value=row.model_id; capacityQuantizations();
      // A benchmark belongs to one exact model and cannot be reused.
      $('capacityBenchmark').value=''; await calculateCapacity();
    }));
    tr.append(modelCell);
    for (const value of [row.quantization,row.weights_gib+' GiB',row.memory_gpu_count ?? t('Does not fit'),row.ram_gib ? row.ram_gib+' GiB' : '—',row.cpu_physical_cores ?? '—']) tr.append(element('td','',String(value)));
    return tr;
  }));
  const method = $('capacityMethod'); method.replaceChildren();
  for (const text of [
    'All calculations run locally. Selecting a profile does not download, install, or activate a model.',
    'Each GPU holds one complete model replica. Small cards are not combined into one memory pool. KV cache uses FP16.',
    'KV bytes = 2 × attention layers × KV heads × head dimension × context tokens × 2 bytes. Hybrid models also include a heuristic recurrent-state reserve.',
    'GPU reserve is the larger of 1.5 GiB or 10% of weights. Headroom applies to weights, reserve, and all active sequence caches.',
    'CPU and RAM figures are engineering heuristics. Corpus size, ingestion, GPU bandwidth, batching, interconnect, and time to first token need separate validation.'
  ]) method.append(element('p','',t(text)));
  method.append(element('small','',t('Catalog verification date') + ': ' + r.catalog_date));
  const sources = element('ul');
  for (const source of r.sources) {
    const item = element('li');
    if (source.startsWith('https://')) {const a=element('a','',source); a.href=source;a.target='_blank';a.rel='noreferrer';item.append(a);}
    else item.textContent=source;
    sources.append(item);
  }
  method.append(sources);
}
$('capacityForm').addEventListener('submit', event=>{event.preventDefault();calculateCapacity();});
$('capacityForm').addEventListener('input',()=>{
  // Hide stale results until the changed inputs have been calculated.
  capacityResult=null; $('capacityResults').replaceChildren(element('div','card',t('Inputs changed. Calculate to update the plan.')));
  $('capacityComparison').hidden=true;
});
$('capacityModel').addEventListener('change',()=>{if(capacityCatalog)capacityQuantizations();$('capacityBenchmark').value='';});
$('capacityQuant').addEventListener('change',()=>{$('capacityBenchmark').value='';});
$('capacityGpu').addEventListener('change',()=>{$('capacityBenchmark').value='';});
$('capacityContext').addEventListener('change',()=>{$('capacityBenchmark').value='';});
$('exportCapacity').addEventListener('click',()=>{
  if(!capacityResult)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(capacityResult,null,2)],{type:'application/json'}));
  const a=element('a');a.href=url;a.download='hardware-plan.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
window.addEventListener('expert-language-change',()=>{if(capacityCatalog)capacityModels();renderCapacity();});

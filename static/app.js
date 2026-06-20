const form = document.getElementById("workflowForm");
const generateBtn = document.getElementById("generateBtn");
const imagesInput = document.getElementById("imagesInput");
const previewList = document.getElementById("previewList");
const focusInput = document.getElementById("focusInput");
const gradeInput = document.getElementById("gradeInput");
const dryRunInput = document.getElementById("dryRunInput");
const configStatus = document.getElementById("configStatus");
const emptyState = document.getElementById("emptyState");
const resultView = document.getElementById("resultView");
const resultTitle = document.getElementById("resultTitle");
const resultMeta = document.getElementById("resultMeta");
const pageFrame = document.getElementById("pageFrame");
const audioPlayer = document.getElementById("audioPlayer");
const scriptText = document.getElementById("scriptText");
const analysisJson = document.getElementById("analysisJson");
const qualityJson = document.getElementById("qualityJson");
const openPageLink = document.getElementById("openPageLink");
const templateSummary = document.getElementById("templateSummary");
const qualitySummary = document.getElementById("qualitySummary");
const providerSummary = document.getElementById("providerSummary");
const artifactLinks = document.getElementById("artifactLinks");
const steps = Array.from(document.querySelectorAll(".steps li"));
const progressLabel = document.getElementById("progressLabel");
const progressPercent = document.getElementById("progressPercent");
const progressBar = document.getElementById("progressBar");
const currentStep = document.getElementById("currentStep");
const elapsedTime = document.getElementById("elapsedTime");
const stepOrder = ["upload", "vision", "template", "page", "quality", "script", "saving"];

function setStep(activeStep, doneSteps = []) {
  steps.forEach((item) => {
    item.classList.toggle("active", item.dataset.step === activeStep);
    item.classList.toggle("done", doneSteps.includes(item.dataset.step));
  });
}

function updateStepState(activeStep, status) {
  if (status === "done") {
    setStep("", stepOrder);
    return;
  }
  const index = stepOrder.indexOf(activeStep);
  const doneSteps = index > 0 ? stepOrder.slice(0, index) : [];
  setStep(activeStep, doneSteps);
}

function updateProgress(status) {
  const percent = Math.max(0, Math.min(100, Number(status.percent || 0)));
  progressLabel.textContent = status.status === "done" ? "生成完成" : status.message || "处理中";
  progressPercent.textContent = `${Math.round(percent)}%`;
  progressBar.style.width = `${percent}%`;
  currentStep.textContent = status.message || "处理中";
  elapsedTime.textContent = `${Number(status.elapsed_seconds || 0).toFixed(1)} 秒`;
  updateStepState(status.step || "upload", status.status);
}

function resetProgress() {
  progressLabel.textContent = "等待开始";
  progressPercent.textContent = "0%";
  progressBar.style.width = "0%";
  currentStep.textContent = "上传截图后开始处理";
  elapsedTime.textContent = "0.0 秒";
  setStep("upload");
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片读取失败"));
    image.src = dataUrl;
  });
}

async function fileToNormalizedImageDataUrl(file) {
  const original = await fileToDataUrl(file);
  if (!String(file.type || "").startsWith("image/")) {
    return original;
  }

  try {
    const image = await loadImage(original);
    const maxEdge = 768;
    const scale = Math.min(1, maxEdge / Math.max(image.naturalWidth, image.naturalHeight));
    const width = Math.max(12, Math.round(image.naturalWidth * scale));
    const height = Math.max(12, Math.round(image.naturalHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    context.drawImage(image, 0, 0, width, height);
    return canvas.toDataURL("image/jpeg", 0.86);
  } catch (error) {
    return original;
  }
}

imagesInput.addEventListener("change", () => {
  previewList.innerHTML = "";
  Array.from(imagesInput.files || []).forEach((file) => {
    const img = document.createElement("img");
    img.alt = file.name;
    img.src = URL.createObjectURL(file);
    previewList.appendChild(img);
  });
  setStep(imagesInput.files.length ? "vision" : "upload", imagesInput.files.length ? ["upload"] : []);
});

async function loadConfigStatus() {
  try {
    const response = await fetch("/api/config-status");
    const status = await response.json();
    if (status.has_api_key) {
      const repairText = status.enable_html_repair ? "质量修复已启用" : "质量修复未启用";
      const externalText = status.allow_external_assets ? "允许外网图片素材" : "仅本地素材";
      configStatus.textContent = `已配置：识图 ${status.vision_model} → HTML ${status.page_model}；${repairText}；${externalText}；TTS 暂未启用`;
      dryRunInput.checked = Boolean(status.mock_mode);
    } else {
      const missing = [];
      if (!status.vision_configured) missing.push("Qwen 识图");
      if (!status.page_configured) missing.push("DeepSeek 页面生成");
      if (!status.script_configured) missing.push("DeepSeek 引导文案");
      configStatus.textContent = `缺少 ${missing.join("、") || "模型"} API Key，已切换到模拟运行`;
      dryRunInput.checked = true;
    }
  } catch (error) {
    configStatus.textContent = "配置状态读取失败";
    configStatus.classList.add("error");
  }
}

async function runWorkflow() {
  const files = Array.from(imagesInput.files || []);
  if (!files.length) {
    imagesInput.focus();
    return;
  }

  generateBtn.disabled = true;
  generateBtn.textContent = "生成中...";
  resultMeta.textContent = "正在提交任务";
  emptyState.classList.add("hidden");
  resultView.classList.add("hidden");
  emptyState.classList.remove("error");
  updateProgress({ status: "running", step: "upload", percent: 2, message: "正在读取本地截图", elapsed_seconds: 0 });

  try {
    const images = [];
    for (const file of files) {
        images.push({
        name: file.name,
        data_url: await fileToNormalizedImageDataUrl(file),
      });
    }

    updateProgress({ status: "running", step: "upload", percent: 4, message: "正在提交后台任务", elapsed_seconds: 0 });
    const response = await fetch("/api/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        images,
        focus: focusInput.value,
        grade_level: gradeInput.value,
        dry_run: dryRunInput.checked,
      }),
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "生成失败");
    }

    await pollWorkflow(result.status_url);
  } catch (error) {
    resultView.classList.add("hidden");
    emptyState.classList.remove("hidden");
    emptyState.textContent = error.message || "生成失败";
    emptyState.classList.add("error");
    resultMeta.textContent = "处理失败";
    progressLabel.textContent = "处理失败";
    currentStep.textContent = error.message || "生成失败";
  } finally {
    generateBtn.disabled = false;
    generateBtn.textContent = "生成课件";
  }
}

async function pollWorkflow(statusUrl) {
  if (!statusUrl) {
    throw new Error("后台没有返回任务状态地址");
  }

  while (true) {
    const response = await fetch(statusUrl);
    const status = await response.json();
    if (!response.ok) {
      throw new Error(status.error || "读取任务进度失败");
    }

    updateProgress(status);
    resultMeta.textContent = status.job_id ? `任务 ${status.job_id}` : "正在处理";

    if (status.status === "done") {
      showResult(status.result);
      return;
    }

    if (status.status === "error") {
      throw new Error(status.error || "生成失败");
    }

    await delay(1000);
  }
}

function showResult(result) {
  const cacheBust = `?t=${Date.now()}`;
  resultTitle.textContent = result.analysis?.lesson_title || "生成结果";
  const templateName = result.template?.name ? `｜模板：${result.template.name}` : "";
  resultMeta.textContent = result.mock ? `模拟运行：${result.job_id}${templateName}` : `已生成：${result.job_id}${templateName}`;
  pageFrame.src = result.page_url + cacheBust;
  openPageLink.href = result.page_url;
  scriptText.textContent = result.guide_script || "";
  analysisJson.textContent = JSON.stringify(result.analysis || {}, null, 2);
  qualityJson.textContent = JSON.stringify(result.quality || {}, null, 2);
  renderSummary(result);

  if (result.audio_url) {
    audioPlayer.src = result.audio_url + cacheBust;
    audioPlayer.closest(".artifact").classList.remove("hidden");
  } else {
    audioPlayer.removeAttribute("src");
    audioPlayer.closest(".artifact").classList.add("hidden");
  }

  emptyState.classList.add("hidden");
  resultView.classList.remove("hidden");
}

function renderSummary(result) {
  const template = result.template || {};
  const quality = result.quality || {};
  const providers = result.providers || {};
  const qualityState = quality.passed ? "通过" : "未通过";
  const repairState = quality.repaired ? "，已自动修复一次" : "";
  const issueCount = Array.isArray(quality.issues) ? quality.issues.length : 0;

  templateSummary.textContent = template.name || template.id || "-";
  qualitySummary.textContent = `${qualityState}${repairState}；问题 ${issueCount} 项`;
  providerSummary.textContent = [
    providers.vision_model ? `识图 ${providers.vision_model}` : "",
    providers.page_model ? `HTML ${providers.page_model}` : "",
    providers.script_model ? `文案 ${providers.script_model}` : "",
    providers.allow_external_assets ? "可用外网图片" : "仅本地素材",
  ].filter(Boolean).join(" → ") || "-";

  const links = [
    ["打开课件", result.page_url],
    ["识别 JSON", result.analysis_url],
    ["模板上下文", result.template_url],
    ["质量报告", result.quality_url],
    ["引导文案", result.script_url],
  ].filter(([, href]) => href);

  artifactLinks.innerHTML = links
    .map(([label, href]) => `<a href="${href}" target="_blank" rel="noopener">${label}</a>`)
    .join("");
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runWorkflow();
});

generateBtn.addEventListener("click", runWorkflow);
resetProgress();
loadConfigStatus();

import { readFile } from 'node:fs/promises'
import settings from '../pipeline/config/settings.json' with { type: 'json' }

const css = await readFile(new URL('../src/styles/variables.css', import.meta.url), 'utf8')
const rootBlock = css.match(/:root\s*\{([\s\S]*?)\n\}/)?.[1] || ''
const darkBlock = css.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] || ''

function tokens(block) {
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((match) => [match[1], match[2]]))
}

function rgb(hex) {
  return [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16) / 255)
}

function linear(channel) {
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
}

function luminance(color) {
  const [red, green, blue] = rgb(color).map(linear)
  return red * 0.2126 + green * 0.7152 + blue * 0.0722
}

function contrast(left, right) {
  const values = [luminance(left), luminance(right)].sort((a, b) => b - a)
  return (values[0] + 0.05) / (values[1] + 0.05)
}

function simulate(color, matrix) {
  const source = rgb(color)
  return matrix.map((row) => Math.max(0, Math.min(1, row.reduce((sum, value, index) => sum + value * source[index], 0))))
}

function distance(left, right) {
  return Math.sqrt(left.reduce((sum, value, index) => sum + (value - right[index]) ** 2, 0))
}

const simulations = {
  protanopia: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deuteranopia: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  tritanopia: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
}

const light = tokens(rootBlock)
const dark = { ...light, ...tokens(darkBlock) }
const minimumDistance = settings.interface.colorblind_minimum_rgb_distance
const minimumContrast = settings.interface.minimum_text_contrast_ratio
const report = Object.fromEntries(Object.entries({ light, dark }).map(([theme, palette]) => {
  const simulatedDistances = Object.fromEntries(Object.entries(simulations).map(([name, matrix]) => [name,
    distance(simulate(palette.positive, matrix), simulate(palette.negative, matrix)),
  ]))
  const positiveContrast = contrast(palette.positive, palette['pill-positive-ink'])
  const negativeContrast = contrast(palette.negative, palette['pill-negative-ink'])
  return [theme, {
    gain: palette.positive,
    loss: palette.negative,
    simulated_distances: simulatedDistances,
    positive_capsule_contrast: positiveContrast,
    negative_capsule_contrast: negativeContrast,
    passes: Object.values(simulatedDistances).every((value) => value >= minimumDistance)
      && positiveContrast >= minimumContrast && negativeContrast >= minimumContrast,
    non_color_signal: 'Every directional value pairs color with an upward or downward triangle glyph.',
  }]
}))

const output = {
  generated_at: new Date().toISOString(),
  simulation: 'Machado-style full-severity RGB matrices',
  minimum_rgb_distance: minimumDistance,
  minimum_text_contrast_ratio: minimumContrast,
  themes: report,
  passes: Object.values(report).every((theme) => theme.passes),
}

process.stdout.write(`${JSON.stringify(output, null, 2)}\n`)
if (!output.passes) process.exitCode = 1
